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
