import { PublicClientApplication, InteractionRequiredAuthError } from '@azure/msal-browser';
import './style.css';

const byId = (id) => document.getElementById(id);
const status = byId('status');
let auth;
let config;
let busy = false;

function updateAccount() {
  const account = auth.getActiveAccount();
  byId('signin').hidden = Boolean(account);
  byId('signout').hidden = !account;
  byId('question-form').hidden = !account;
  status.textContent = account ? `Signed in as ${account.name || account.username || 'a member'}.` : 'Sign in to search the shared documents.';
}

async function start() {
  const response = await fetch('/api/config');
  if (!response.ok) throw new Error('Configuration unavailable');
  config = await response.json();
  auth = new PublicClientApplication({
    auth: { clientId: config.clientId, authority: config.authority,
      knownAuthorities: [new URL(config.authority).hostname], redirectUri: config.redirectUri,
      postLogoutRedirectUri: config.redirectUri, navigateToLoginRequestUrl: false },
    cache: { cacheLocation: 'sessionStorage' },
  });
  await auth.initialize();
  const result = await auth.handleRedirectPromise();
  if (result?.account) auth.setActiveAccount(result.account);
  if (!auth.getActiveAccount()) {
    const accounts = auth.getAllAccounts();
    if (accounts.length === 1) auth.setActiveAccount(accounts[0]);
  }
  byId('signin').disabled = false;
  updateAccount();
}

byId('signin').addEventListener('click', async () => {
  try { await auth.loginRedirect({ scopes: [config.scope] }); }
  catch { status.textContent = 'Sign-in could not start. Please try again.'; }
});

byId('signout').addEventListener('click', async () => {
  byId('result').hidden = true;
  byId('answer').textContent = '';
  byId('question').value = '';
  try { await auth.logoutRedirect({ account: auth.getActiveAccount() }); }
  catch { status.textContent = 'Sign-out failed. Please try again.'; }
});

byId('question-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  const question = byId('question').value.trim();
  if (busy || !question) return;
  busy = true;
  byId('ask').disabled = true;
  byId('result').hidden = true;
  status.textContent = 'Searching the documents…';
  try {
    const token = await auth.acquireTokenSilent({ scopes: [config.scope], account: auth.getActiveAccount() });
    const response = await fetch('/api/chat', {
      method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token.accessToken}` },
      body: JSON.stringify({ question, top_k: 5 }), signal: AbortSignal.timeout(220000),
    });
    const result = await response.json();
    if (!response.ok) {
      const reference = response.headers.get('x-request-id');
      const message = typeof result.detail === 'string' ? result.detail : 'The request could not be completed.';
      status.textContent = `${message}${reference ? ` Reference: ${reference}` : ''}`;
      return;
    }
    // Render model and document text as text, never as HTML.
    byId('answer').textContent = result.answer;
    byId('sources').replaceChildren();
    for (const source of result.sources) {
      const item = document.createElement('li');
      item.textContent = `[${source.citation}] ${source.source}${source.page ? ` · Page ${source.page}` : ''}`;
      byId('sources').append(item);
    }
    byId('sources-heading').hidden = result.sources.length === 0;
    byId('result').hidden = false;
    status.textContent = 'Answer ready.';
  } catch (error) {
    if (error instanceof InteractionRequiredAuthError) {
      await auth.acquireTokenRedirect({ scopes: [config.scope] });
    } else {
      status.textContent = 'The service could not be reached. Please try again.';
    }
  } finally {
    busy = false;
    byId('ask').disabled = false;
  }
});

start().catch(() => { status.textContent = 'Sign-in is unavailable. Please try again later.'; });
