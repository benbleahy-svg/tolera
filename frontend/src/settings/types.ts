/** Email connectivity types (M3.5 — spec #email-connectivity). */

export type EmailConnectionType = 'gmail' | 'outlook' | 'smtp_imap';

export interface EmailConnection {
  id: string;
  connection_type: EmailConnectionType;
  from_address: string;
  from_name: string | null;
  is_primary: boolean;
  last_synced_at: string | null;
  last_sync_error: string | null;
  created_at: string;
}

export interface SmtpConnectionBody {
  from_address: string;
  from_name?: string | null;
  smtp_host: string;
  smtp_port?: number;
  imap_host: string;
  imap_port?: number;
  username: string;
  password: string;
}

export interface EmailAttachmentMeta {
  filename: string;
  storage_key: string;
  size_bytes: number;
  content_type: string | null;
}

export interface EmailMessage {
  id: string;
  direction: 'outbound' | 'inbound';
  from_address: string;
  to_addresses: string[];
  subject: string | null;
  body_text: string | null;
  body_html: string | null;
  attachments: EmailAttachmentMeta[];
  sent_at: string | null;
  created_at: string;
}

export interface SendEmailBody {
  to: string[];
  subject: string;
  body_text: string;
}

/* ---- Email templates + send-quote composer (M5.5, spec #email-templates) ---- */

export type EmailTemplateType = 'quote_send' | 'order_shipment' | 'order_refund';

export interface EmailTemplate {
  id: string;
  template_type: EmailTemplateType;
  name: string;
  subject: string;
  body: string;
  is_default: boolean;
  locale: string;
  last_edited_by: string | null;
  updated_at: string;
}

export interface EmailTemplateCreateBody {
  template_type: EmailTemplateType;
  name: string;
  subject: string;
  body: string;
  is_default?: boolean;
  locale?: string;
}

export interface EmailTemplateUpdateBody {
  name?: string;
  subject?: string;
  body?: string;
  is_default?: boolean;
}

export interface SendQuoteBody {
  to: string[];
  cc: string[];
  bcc: string[];
  template_id?: string | null;
  subject: string;
  body_html: string;
  include_pdf: boolean;
}

export interface SendQuoteResult {
  quote_id: string;
  status: string;
  recipients: string[];
  pdf_attached: boolean;
}

export interface SendQuotePreview {
  subject: string;
  body_html: string;
}
