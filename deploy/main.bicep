targetScope = 'resourceGroup'

@description('Name of the new web application. Do not use the existing Chroma app name.')
param appName string = 'rag-web'
param location string = resourceGroup().location
@description('Full resource ID of the existing Container Apps environment.')
param environmentId string
@description('Existing Azure Container Registry login server, e.g. registry.azurecr.io.')
param registryServer string
@description('Full versioned image reference, preferably an immutable digest.')
param image string
@description('User-assigned identity already granted ACR pull and model inference permissions.')
param identityResourceId string
param identityClientId string
@description('Non-secret configuration only. See parameters.example.json.')
param environmentVariables object
@description('Optional Key Vault references: { name, envName, keyVaultUrl }. No raw secret values.')
param keyVaultSecrets array = []

var regularEnvironment = [for setting in items(environmentVariables): { name: setting.key, value: string(setting.value) }]
var secretEnvironment = [for secret in keyVaultSecrets: { name: secret.envName, secretRef: secret.name }]

resource web 'Microsoft.App/containerApps@2024-03-01' = {
  name: appName
  location: location
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${identityResourceId}': {} }
  }
  properties: {
    managedEnvironmentId: environmentId
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
      registries: [{ server: registryServer, identity: identityResourceId }]
      secrets: [for secret in keyVaultSecrets: {
        name: secret.name
        keyVaultUrl: secret.keyVaultUrl
        identity: identityResourceId
      }]
    }
    template: {
      terminationGracePeriodSeconds: 240
      containers: [{
        name: 'web'
        image: image
        resources: { cpu: 1, memory: '2Gi' }
        env: concat(
          regularEnvironment,
          secretEnvironment,
          [{ name: 'APP_ENV', value: 'production' }, { name: 'AZURE_CLIENT_ID', value: identityClientId }]
        )
        probes: [
          { type: 'Startup', httpGet: { path: '/health/live', port: 8000 }, periodSeconds: 5, timeoutSeconds: 3, failureThreshold: 60 }
          { type: 'Liveness', httpGet: { path: '/health/live', port: 8000 }, periodSeconds: 30, timeoutSeconds: 3, failureThreshold: 3 }
          { type: 'Readiness', httpGet: { path: '/health/ready', port: 8000 }, periodSeconds: 30, timeoutSeconds: 25, failureThreshold: 3 }
        ]
      }]
      // Limits are process-local. Add a distributed quota before increasing replicas/workers.
      scale: { minReplicas: 1, maxReplicas: 1 }
    }
  }
}

output url string = 'https://${web.properties.configuration.ingress.fqdn}'
output appResourceId string = web.id
