/**
 * Email-connectivity API (M3.5) — connection management for the settings page
 * and the quote communications timeline, bound to the Clerk session token once
 * (the `useQuotesApi` pattern; tests mock this module wholesale).
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiFetch, type TokenGetter } from '../api/client';
import type {
  EmailConnection,
  EmailMessage,
  EmailTemplate,
  EmailTemplateCreateBody,
  EmailTemplateType,
  EmailTemplateUpdateBody,
  SendEmailBody,
  SendQuoteBody,
  SendQuotePreview,
  SendQuoteResult,
  SmtpConnectionBody,
} from './types';

export interface EmailApi {
  listConnections: () => Promise<EmailConnection[]>;
  connectSmtp: (body: SmtpConnectionBody) => Promise<EmailConnection>;
  disconnect: (id: string) => Promise<void>;
  setPrimary: (id: string) => Promise<EmailConnection>;
  testConnection: (id: string) => Promise<{ status: string; subject: string }>;
  oauthStart: (provider: 'gmail' | 'outlook') => Promise<{ authorize_url: string }>;
  getQuoteEmails: (quoteId: string) => Promise<EmailMessage[]>;
  sendQuoteEmail: (quoteId: string, body: SendEmailBody) => Promise<EmailMessage>;
  /** M5.5 — the full send-quote composer (templates + merge fields + PDF). */
  sendQuote: (quoteId: string, body: SendQuoteBody) => Promise<SendQuoteResult>;
  previewQuoteSend: (quoteId: string, body: SendQuoteBody) => Promise<SendQuotePreview>;
}

/** Email-template CRUD (M5.5, spec #email-templates). */
export interface EmailTemplatesApi {
  list: (type?: EmailTemplateType) => Promise<EmailTemplate[]>;
  create: (body: EmailTemplateCreateBody) => Promise<EmailTemplate>;
  get: (id: string) => Promise<EmailTemplate>;
  update: (id: string, body: EmailTemplateUpdateBody) => Promise<EmailTemplate>;
  remove: (id: string) => Promise<void>;
}

/** Build an email API client bound to the current Clerk session token. */
export function useEmailApi(): EmailApi {
  const { getToken } = useAuth();
  return useMemo<EmailApi>(() => {
    const token: TokenGetter = () => getToken();
    return {
      listConnections: () => apiFetch('/api/email-connections', token),
      connectSmtp: (body) =>
        apiFetch('/api/email-connections/smtp', token, { method: 'POST', body }),
      disconnect: (id) => apiFetch(`/api/email-connections/${id}`, token, { method: 'DELETE' }),
      setPrimary: (id) =>
        apiFetch(`/api/email-connections/${id}/primary`, token, { method: 'PUT' }),
      testConnection: (id) =>
        apiFetch(`/api/email-connections/${id}/test`, token, { method: 'POST' }),
      oauthStart: (provider) => apiFetch(`/api/email-connections/oauth/${provider}/start`, token),
      getQuoteEmails: (quoteId) => apiFetch(`/api/quotes/${quoteId}/emails`, token),
      sendQuoteEmail: (quoteId, body) =>
        apiFetch(`/api/quotes/${quoteId}/emails`, token, { method: 'POST', body }),
      sendQuote: (quoteId, body) =>
        apiFetch(`/api/quotes/${quoteId}/send`, token, { method: 'POST', body }),
      previewQuoteSend: (quoteId, body) =>
        apiFetch(`/api/quotes/${quoteId}/send/preview`, token, { method: 'POST', body }),
    };
  }, [getToken]);
}

/** Build an email-template CRUD client bound to the current Clerk session token. */
export function useEmailTemplatesApi(): EmailTemplatesApi {
  const { getToken } = useAuth();
  return useMemo<EmailTemplatesApi>(() => {
    const token: TokenGetter = () => getToken();
    return {
      list: (type) =>
        apiFetch(
          type ? `/api/email-templates?template_type=${type}` : '/api/email-templates',
          token,
        ),
      create: (body) => apiFetch('/api/email-templates', token, { method: 'POST', body }),
      get: (id) => apiFetch(`/api/email-templates/${id}`, token),
      update: (id, body) =>
        apiFetch(`/api/email-templates/${id}`, token, { method: 'PATCH', body }),
      remove: (id) => apiFetch(`/api/email-templates/${id}`, token, { method: 'DELETE' }),
    };
  }, [getToken]);
}
