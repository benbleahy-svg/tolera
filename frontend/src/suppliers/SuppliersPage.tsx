/**
 * Supplier Directory — the `/suppliers` destination (spec #vendor-rfq → "Supplier
 * Directory (nav: Suppliers)"). Lists the active org's vendors with the spec's
 * four columns (Vendor name · Processes chips · Materials chips · Active RFQs),
 * a toolbar of search + process/material filters, and ADD VENDOR (gated on
 * `config_edit`).
 *
 * Active RFQs reads 0 for every vendor until M6.4 creates the first `VendorRFQ` —
 * the column is honest, not a placeholder (see `app.vendors._active_rfq_counts`).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { useHasPermission } from '../session/session';
import { CreateVendorModal } from './CreateVendorModal';
import { type Vendor, useVendorsApi } from './api';

/** The capability chips of one axis, or an em-dash when the vendor has none. */
export function TagChips({ tags, label }: { tags: string[]; label: string }) {
  if (tags.length === 0) return <span aria-label={label}>—</span>;
  return (
    <span className="crm-chips" aria-label={label}>
      {tags.map((tag) => (
        <span key={tag} className="crm-chip">
          {tag}
        </span>
      ))}
    </span>
  );
}

export function SuppliersPage() {
  const { t } = useTranslation();
  const api = useVendorsApi();
  const canEdit = useHasPermission('config_edit');

  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [q, setQ] = useState('');
  const [process, setProcess] = useState('');
  const [material, setMaterial] = useState('');
  const [includeArchived, setIncludeArchived] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const requestSeq = useRef(0);

  const load = useCallback(() => {
    const seq = ++requestSeq.current;
    setError(null);
    api
      .listVendors({
        q: q.trim() || undefined,
        process: process.trim() || undefined,
        material: material.trim() || undefined,
        includeArchived,
      })
      .then((next) => {
        // Ignore a slow earlier request that resolves after a newer one.
        if (seq === requestSeq.current) setVendors(next);
      })
      .catch((e: unknown) => {
        if (seq === requestSeq.current) {
          setError(e instanceof ApiError ? e.message : String(e));
        }
      });
  }, [api, q, process, material, includeArchived]);

  useEffect(() => {
    const handle = setTimeout(load, 200); // debounce search/filter keystrokes
    return () => clearTimeout(handle);
  }, [load]);

  return (
    <section className="page">
      <div className="crm-header">
        <h1 className="page-title">{t('nav.suppliers')}</h1>
        {canEdit && (
          <button type="button" className="btn btn-primary" onClick={() => setCreating(true)}>
            {t('suppliers.add_vendor')}
          </button>
        )}
      </div>

      <div className="crm-toolbar">
        <input
          className="crm-search"
          type="search"
          value={q}
          placeholder={t('suppliers.search_placeholder')}
          aria-label={t('suppliers.search_placeholder')}
          onChange={(e) => setQ(e.target.value)}
        />
        <input
          className="crm-search"
          type="search"
          value={process}
          placeholder={t('suppliers.filter_process')}
          aria-label={t('suppliers.filter_process')}
          onChange={(e) => setProcess(e.target.value)}
        />
        <input
          className="crm-search"
          type="search"
          value={material}
          placeholder={t('suppliers.filter_material')}
          aria-label={t('suppliers.filter_material')}
          onChange={(e) => setMaterial(e.target.value)}
        />
        <label className="crm-toggle">
          <input
            type="checkbox"
            checked={includeArchived}
            onChange={(e) => setIncludeArchived(e.target.checked)}
          />
          {t('suppliers.show_archived')}
        </label>
      </div>

      {error && (
        <p className="crm-error" role="alert">
          {error}
        </p>
      )}

      {vendors.length === 0 ? (
        <p className="page-empty">{t('suppliers.empty')}</p>
      ) : (
        <table className="crm-table">
          <thead>
            <tr>
              <th>{t('suppliers.col.name')}</th>
              <th>{t('suppliers.col.processes')}</th>
              <th>{t('suppliers.col.materials')}</th>
              <th>{t('suppliers.col.active_rfqs')}</th>
            </tr>
          </thead>
          <tbody>
            {vendors.map((vendor) => (
              <tr key={vendor.id}>
                <td>
                  <Link to={`/suppliers/${vendor.id}`}>{vendor.name}</Link>
                  {vendor.status === 'inactive' && (
                    <span className="crm-chip crm-chip-archived">
                      {t('suppliers.status.inactive')}
                    </span>
                  )}
                  {/* Archived is orthogonal to inactive — with "Show archived" on,
                      an archived-but-active vendor would otherwise look ordinary. */}
                  {vendor.archived && (
                    <span className="crm-chip crm-chip-archived">
                      {t('suppliers.status.archived')}
                    </span>
                  )}
                </td>
                <td>
                  <TagChips tags={vendor.capabilities.processes} label={t('suppliers.col.processes')} />
                </td>
                <td>
                  <TagChips tags={vendor.capabilities.materials} label={t('suppliers.col.materials')} />
                </td>
                <td>{vendor.active_rfq_count}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {creating && (
        <CreateVendorModal
          onClose={() => setCreating(false)}
          onCreated={() => {
            setCreating(false);
            load();
          }}
        />
      )}
    </section>
  );
}
