/**
 * Vendor detail — the four tabs the spec fixes for `#vendor-rfq` → "Vendor Detail
 * — Tabs":
 *
 *   Overview      company / quoting contacts / address / ERP sync status / Active-Inactive
 *   RFQ History   every RFQ sent to this vendor — read-only here, filled from M6.4
 *   Capabilities  editable process + material tags (drives the directory filter)
 *   Notes         internal only — the copy says so, and the backend's external DTO
 *                 cannot serialize it, so it can never reach the vendor
 *
 * ERP-sourced vendors (`erp_managed`) render their identity fields read-only with
 * an explaining hint: the sync is one-way ERP → Tolera. Capabilities and Notes
 * stay editable — that is BF-only data which never writes back.
 */

import { useCallback, useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { useHasPermission } from '../session/session';
import { splitTagInput } from './tags';
import {
  type Vendor,
  type VendorContact,
  type VendorRfqHistoryEntry,
  useVendorsApi,
} from './api';

type TabKey = 'overview' | 'rfq_history' | 'capabilities' | 'notes';

const TABS: TabKey[] = ['overview', 'rfq_history', 'capabilities', 'notes'];

export function VendorDetailPage() {
  const { t } = useTranslation();
  const { vendorId = '' } = useParams();
  const api = useVendorsApi();
  const canEdit = useHasPermission('config_edit');

  const [vendor, setVendor] = useState<Vendor | null>(null);
  const [contacts, setContacts] = useState<VendorContact[]>([]);
  const [history, setHistory] = useState<VendorRfqHistoryEntry[]>([]);
  const [tab, setTab] = useState<TabKey>('overview');
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setError(null);
    Promise.all([
      api.getVendor(vendorId),
      api.listVendorContacts(vendorId),
      api.listRfqHistory(vendorId),
    ])
      .then(([nextVendor, nextContacts, nextHistory]) => {
        setVendor(nextVendor);
        setContacts(nextContacts);
        setHistory(nextHistory);
      })
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [api, vendorId]);

  useEffect(load, [load]);

  const save = (body: Partial<Vendor>) => {
    setError(null);
    api
      .updateVendor(vendorId, body)
      .then(setVendor)
      .catch((e: unknown) => setError(e instanceof ApiError ? e.message : String(e)));
  };

  if (error && !vendor) {
    return (
      <section className="page">
        <p className="crm-error" role="alert">
          {error}
        </p>
      </section>
    );
  }
  if (!vendor) return <p className="page-empty">{t('suppliers.loading')}</p>;

  return (
    <section className="page">
      <div className="crm-header">
        <div>
          <Link to="/suppliers">{t('suppliers.back_to_directory')}</Link>
          <h1 className="page-title">{vendor.name}</h1>
        </div>
        {canEdit && (
          <button
            type="button"
            className="btn btn-ghost"
            onClick={() =>
              save({ status: vendor.status === 'active' ? 'inactive' : 'active' })
            }
          >
            {vendor.status === 'active'
              ? t('suppliers.actions.deactivate')
              : t('suppliers.actions.activate')}
          </button>
        )}
      </div>

      {vendor.erp_managed && (
        <p className="crm-hint" role="note">
          {t('suppliers.erp_managed_hint', { id: vendor.erp_vendor_id })}
        </p>
      )}
      {error && (
        <p className="crm-error" role="alert">
          {error}
        </p>
      )}

      <div className="crm-tabs" role="tablist">
        {TABS.map((key) => (
          <button
            key={key}
            type="button"
            role="tab"
            aria-selected={tab === key}
            className={tab === key ? 'crm-tab crm-tab-active' : 'crm-tab'}
            onClick={() => setTab(key)}
          >
            {t(`suppliers.tab.${key}`)}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <OverviewTab vendor={vendor} contacts={contacts} canEdit={canEdit} onSave={save} />
      )}
      {tab === 'rfq_history' && <RfqHistoryTab entries={history} />}
      {tab === 'capabilities' && (
        <CapabilitiesTab vendor={vendor} canEdit={canEdit} onSave={save} />
      )}
      {tab === 'notes' && <NotesTab vendor={vendor} canEdit={canEdit} onSave={save} />}
    </section>
  );
}

function OverviewTab({
  vendor,
  contacts,
  canEdit,
  onSave,
}: {
  vendor: Vendor;
  contacts: VendorContact[];
  canEdit: boolean;
  onSave: (body: Partial<Vendor>) => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState(vendor.name);
  const [address, setAddress] = useState(vendor.address ?? '');
  const [vatId, setVatId] = useState(vendor.vat_id ?? '');
  const [phone, setPhone] = useState(vendor.phone ?? '');

  // Identity is ERP-owned on a synced vendor (one-way ERP → Tolera), so those
  // fields are disabled rather than merely rejected by the API on save.
  const identityLocked = !canEdit || vendor.erp_managed;

  return (
    <div role="tabpanel">
      <label className="crm-field">
        <span>{t('suppliers.field.name')}</span>
        <input value={name} disabled={identityLocked} onChange={(e) => setName(e.target.value)} />
      </label>
      <label className="crm-field">
        <span>{t('suppliers.field.address')}</span>
        <textarea
          value={address}
          rows={3}
          disabled={identityLocked}
          onChange={(e) => setAddress(e.target.value)}
        />
      </label>
      <label className="crm-field">
        <span>{t('suppliers.field.vat_id')}</span>
        <input value={vatId} disabled={identityLocked} onChange={(e) => setVatId(e.target.value)} />
      </label>
      <label className="crm-field">
        <span>{t('suppliers.field.phone')}</span>
        <input value={phone} disabled={identityLocked} onChange={(e) => setPhone(e.target.value)} />
      </label>
      {!identityLocked && (
        <button
          type="button"
          className="btn btn-primary"
          disabled={!name.trim()}
          onClick={() =>
            onSave({
              name: name.trim(),
              address: address.trim() || null,
              vat_id: vatId.trim() || null,
              phone: phone.trim() || null,
            })
          }
        >
          {t('suppliers.actions.save')}
        </button>
      )}

      <dl className="crm-detail">
        <dt>{t('suppliers.field.status')}</dt>
        <dd>{t(`suppliers.status.${vendor.status}`)}</dd>
        <dt>{t('suppliers.field.erp_status')}</dt>
        <dd>{vendor.erp_managed ? vendor.erp_vendor_id : t('suppliers.erp_manual')}</dd>
      </dl>

      <h2 className="crm-subtitle">{t('suppliers.quoting_contacts')}</h2>
      {contacts.length === 0 ? (
        <p className="page-empty">{t('suppliers.no_contacts')}</p>
      ) : (
        <ul className="crm-list">
          {contacts.map((contact) => (
            <li key={contact.id}>
              {contact.name ?? contact.email}
              {' — '}
              {contact.email}
              {contact.is_primary && <span className="crm-chip">{t('suppliers.primary')}</span>}
              {contact.cc && <span className="crm-chip">{t('suppliers.cc')}</span>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function RfqHistoryTab({ entries }: { entries: VendorRfqHistoryEntry[] }) {
  const { t } = useTranslation();
  // M6.3 owns the tab; M6.4+ writes its content (the RFQs, their prices per qty
  // break, and which quote a price was applied to).
  if (entries.length === 0) return <p className="page-empty">{t('suppliers.no_rfq_history')}</p>;
  return (
    <ul className="crm-list" role="tabpanel">
      {entries.map((entry) => (
        <li key={entry.id}>{String(entry.id)}</li>
      ))}
    </ul>
  );
}

function CapabilitiesTab({
  vendor,
  canEdit,
  onSave,
}: {
  vendor: Vendor;
  canEdit: boolean;
  onSave: (body: Partial<Vendor>) => void;
}) {
  const { t } = useTranslation();
  const [processes, setProcesses] = useState(vendor.capabilities.processes.join(', '));
  const [materials, setMaterials] = useState(vendor.capabilities.materials.join(', '));

  return (
    <div role="tabpanel">
      <label className="crm-field">
        <span>{t('suppliers.field.processes')}</span>
        <input
          value={processes}
          disabled={!canEdit}
          placeholder={t('suppliers.tag_placeholder')}
          onChange={(e) => setProcesses(e.target.value)}
        />
      </label>
      <label className="crm-field">
        <span>{t('suppliers.field.materials')}</span>
        <input
          value={materials}
          disabled={!canEdit}
          placeholder={t('suppliers.tag_placeholder')}
          onChange={(e) => setMaterials(e.target.value)}
        />
      </label>
      {canEdit && (
        <button
          type="button"
          className="btn btn-primary"
          onClick={() =>
            onSave({
              capabilities: {
                processes: splitTagInput(processes),
                materials: splitTagInput(materials),
              },
            })
          }
        >
          {t('suppliers.actions.save')}
        </button>
      )}
    </div>
  );
}

function NotesTab({
  vendor,
  canEdit,
  onSave,
}: {
  vendor: Vendor;
  canEdit: boolean;
  onSave: (body: Partial<Vendor>) => void;
}) {
  const { t } = useTranslation();
  const [notes, setNotes] = useState(vendor.notes ?? '');

  return (
    <div role="tabpanel">
      {/* The confidentiality rule is enforced server-side (VendorExternalOut cannot
          express notes); this line tells the estimator what the type guarantees. */}
      <p className="crm-hint">{t('suppliers.notes_internal_only')}</p>
      <label className="crm-field">
        <span>{t('suppliers.field.notes')}</span>
        <textarea
          value={notes}
          rows={8}
          disabled={!canEdit}
          onChange={(e) => setNotes(e.target.value)}
        />
      </label>
      {canEdit && (
        <button
          type="button"
          className="btn btn-primary"
          onClick={() => onSave({ notes: notes.trim() || null })}
        >
          {t('suppliers.actions.save')}
        </button>
      )}
    </div>
  );
}
