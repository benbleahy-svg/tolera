/**
 * CRM (Accounts & Contacts) API types + the `useCrmApi` hook (M1.1).
 *
 * Mirrors the FastAPI `/api/accounts` + `/api/contacts` contract. The hook binds
 * each call to the Clerk session token once, so pages call `api.listAccounts()`
 * without threading auth through — and tests mock this module wholesale (no Clerk).
 */

import { apiFetch, type TokenGetter } from '../api/client';
import { useApiClient } from '../api/hooks';

export type AccountType = 'customer' | 'vendor';

export interface Account {
  id: string;
  name: string;
  type: AccountType;
  email: string | null;
  phone: string | null;
  phone_ext: string | null;
  website: string | null;
  notes: string | null;
  salesperson_id: string | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface Contact {
  id: string;
  account_id: string | null;
  email: string;
  first_name: string | null;
  last_name: string | null;
  role: string | null;
  phone: string | null;
  phone_ext: string | null;
  notes: string | null;
  salesperson_id: string | null;
  archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface ContactCreate {
  email: string;
  first_name?: string | null;
  last_name?: string | null;
  role?: string | null;
  phone?: string | null;
  notes?: string | null;
}

export interface AccountCreate {
  name: string;
  type?: AccountType;
  email?: string | null;
  phone?: string | null;
  website?: string | null;
  notes?: string | null;
  primary_contact?: ContactCreate;
}

export interface AccountListParams {
  q?: string;
  includeArchived?: boolean;
}

export interface CrmApi {
  listAccounts: (params?: AccountListParams) => Promise<Account[]>;
  createAccount: (body: AccountCreate) => Promise<Account>;
  getAccount: (id: string) => Promise<Account>;
  updateAccount: (id: string, body: Partial<AccountCreate>) => Promise<Account>;
  archiveAccount: (id: string) => Promise<Account>;
  restoreAccount: (id: string) => Promise<Account>;
  listAccountContacts: (accountId: string) => Promise<Contact[]>;
  createContact: (accountId: string, body: ContactCreate) => Promise<Contact>;
  getContact: (id: string) => Promise<Contact>;
  updateContact: (id: string, body: Partial<ContactCreate>) => Promise<Contact>;
  archiveContact: (id: string) => Promise<Contact>;
  restoreContact: (id: string) => Promise<Contact>;
}

function accountsQuery(params?: AccountListParams): string {
  const search = new URLSearchParams();
  if (params?.q) search.set('q', params.q);
  if (params?.includeArchived) search.set('include_archived', 'true');
  const qs = search.toString();
  return qs ? `?${qs}` : '';
}

function makeCrmApi(token: TokenGetter): CrmApi {
  return {
    listAccounts: (params) => apiFetch(`/api/accounts${accountsQuery(params)}`, token),
    createAccount: (body) => apiFetch('/api/accounts', token, { method: 'POST', body }),
    getAccount: (id) => apiFetch(`/api/accounts/${id}`, token),
    updateAccount: (id, body) => apiFetch(`/api/accounts/${id}`, token, { method: 'PATCH', body }),
    archiveAccount: (id) => apiFetch(`/api/accounts/${id}/archive`, token, { method: 'POST' }),
    restoreAccount: (id) => apiFetch(`/api/accounts/${id}/restore`, token, { method: 'POST' }),
    listAccountContacts: (accountId) => apiFetch(`/api/accounts/${accountId}/contacts`, token),
    createContact: (accountId, body) =>
      apiFetch(`/api/accounts/${accountId}/contacts`, token, { method: 'POST', body }),
    getContact: (id) => apiFetch(`/api/contacts/${id}`, token),
    updateContact: (id, body) => apiFetch(`/api/contacts/${id}`, token, { method: 'PATCH', body }),
    archiveContact: (id) => apiFetch(`/api/contacts/${id}/archive`, token, { method: 'POST' }),
    restoreContact: (id) => apiFetch(`/api/contacts/${id}/restore`, token, { method: 'POST' }),
  };
}

/** Build a CRM API client bound to the current Clerk session token. */
export function useCrmApi(): CrmApi {
  return useApiClient(makeCrmApi);
}
