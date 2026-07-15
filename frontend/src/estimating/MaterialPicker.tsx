/**
 * The nested material picker (spec #partview header: "Material (nested picker +
 * Edit Material Properties + clear)"). A type-ahead over hierarchical paths
 * ("Metall / Aluminium / EN AW-6061") with a browse-tree fallback, plus the
 * Edit-Material-Properties inline form (edits the org-library row) and a clear.
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { ClassNode, MaterialOut, MaterialSearchHit, MaterialUpdateBody } from './types';

interface Props {
  selected: MaterialOut | null;
  selectedPath: string | null;
  search: (q: string) => Promise<MaterialSearchHit[]>;
  loadTree: () => Promise<ClassNode[]>;
  onPick: (materialId: string) => void;
  onClear: () => void;
  onEdit: (materialId: string, body: MaterialUpdateBody) => Promise<void>;
  disabled?: boolean;
}

export function MaterialPicker({
  selected,
  selectedPath,
  search,
  loadTree,
  onPick,
  onClear,
  onEdit,
  disabled,
}: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [hits, setHits] = useState<MaterialSearchHit[]>([]);
  const [tree, setTree] = useState<ClassNode[] | null>(null);
  const [editing, setEditing] = useState(false);
  const [density, setDensity] = useState('');
  const [costPerVolume, setCostPerVolume] = useState('');
  const [leadDays, setLeadDays] = useState('0');
  const seq = useRef(0);

  useEffect(() => {
    if (!open || query.trim() === '') {
      setHits([]);
      return;
    }
    const mySeq = ++seq.current;
    const timer = setTimeout(() => {
      search(query.trim())
        .then((next) => {
          if (mySeq === seq.current) setHits(next);
        })
        .catch(() => {
          if (mySeq === seq.current) setHits([]);
        });
    }, 150);
    return () => clearTimeout(timer);
  }, [open, query, search]);

  useEffect(() => {
    if (open && tree === null) {
      loadTree()
        .then(setTree)
        .catch(() => setTree([]));
    }
  }, [open, tree, loadTree]);

  const pick = (id: string) => {
    setOpen(false);
    setQuery('');
    onPick(id);
  };

  const startEdit = () => {
    if (!selected) return;
    setDensity(selected.density ?? '');
    setCostPerVolume(selected.cost_per_volume ?? '');
    setLeadDays(String(selected.added_lead_time_days));
    setEditing(true);
  };

  const saveEdit = () => {
    if (!selected) return;
    const body: MaterialUpdateBody = {
      density: density.trim() === '' ? null : density.trim(),
      cost_per_volume: costPerVolume.trim() === '' ? null : costPerVolume.trim(),
      added_lead_time_days: Number(leadDays) || 0,
    };
    void onEdit(selected.id, body).then(() => setEditing(false));
  };

  return (
    <div className="est-material-picker">
      <span className="est-field-label">{t('estimating.material')}</span>
      {selected ? (
        <span className="est-material-selected">
          {/* full hierarchical path inline (frames show "Metal / Aluminum / …") */}
          <span>{selectedPath ?? selected.display_name}</span>
          <button type="button" onClick={startEdit} disabled={disabled}>
            {t('estimating.edit_material_properties')}
          </button>
          <button type="button" onClick={onClear} disabled={disabled} aria-label={t('estimating.clear_material')}>
            ×
          </button>
        </span>
      ) : (
        <button type="button" onClick={() => setOpen((v) => !v)} disabled={disabled}>
          {t('estimating.pick_material')}
        </button>
      )}
      {selected && (
        <button type="button" onClick={() => setOpen((v) => !v)} disabled={disabled}>
          {t('estimating.change_material')}
        </button>
      )}
      {open && (
        <div className="est-picker-pop" role="dialog">
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('estimating.material_search_placeholder')}
            aria-label={t('estimating.material_search_placeholder')}
          />
          {hits.length > 0 && (
            <ul className="est-picker-hits">
              {hits.map((hit) => (
                <li key={hit.id}>
                  <button type="button" onClick={() => pick(hit.id)}>
                    {hit.path}
                    {hit.aisi_alias ? ` (${hit.aisi_alias})` : ''}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {query.trim() === '' && tree && (
            <div className="est-picker-tree">
              {tree.map((cls) => (
                <details key={cls.id} open={tree.length === 1}>
                  <summary>{cls.name}</summary>
                  {cls.families.map((family) => (
                    <details key={family.id}>
                      <summary>{family.name}</summary>
                      <ul>
                        {family.materials.map((material) => (
                          <li key={material.id}>
                            <button type="button" onClick={() => pick(material.id)}>
                              {material.display_name}
                              {material.aisi_alias ? ` (${material.aisi_alias})` : ''}
                            </button>
                          </li>
                        ))}
                      </ul>
                    </details>
                  ))}
                </details>
              ))}
            </div>
          )}
        </div>
      )}
      {editing && selected && (
        <div className="est-picker-pop" role="dialog" aria-label={t('estimating.edit_material_properties')}>
          <label>
            {t('estimating.density')}
            <input value={density} onChange={(e) => setDensity(e.target.value)} />
          </label>
          <label>
            {t('estimating.cost_per_volume')}
            <input value={costPerVolume} onChange={(e) => setCostPerVolume(e.target.value)} />
          </label>
          <label>
            {t('estimating.added_lead_time_days')}
            <input value={leadDays} onChange={(e) => setLeadDays(e.target.value)} />
          </label>
          <div className="est-actions">
            <button type="button" onClick={() => setEditing(false)}>
              {t('common.cancel')}
            </button>
            <button type="button" onClick={saveEdit}>
              {t('common.save')}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
