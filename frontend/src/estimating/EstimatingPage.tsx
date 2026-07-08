/**
 * Part-estimating view, M1.7 cut (spec #partview): for a quote's line item —
 * header assignments (Process + Change Process, Material nested picker + Edit
 * Material Properties + clear), the Materials and Operations sections with
 * per-quantity cost columns, the operation drawer (Calculated vs Override), and
 * the roll-up input summary (#costing: Raw Material / Inside / Outside per
 * break). Route: /quotes/:quoteId — the M1.4 quote detail screen proper arrives
 * with later blocks; this page is the Materials & Operations slice.
 */

import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { useHasPermission } from '../session/session';
import { useEstimatingApi } from './api';
import { ChangeProcessModal } from './ChangeProcessModal';
import { MaterialPicker } from './MaterialPicker';
import { OperationDrawer } from './OperationDrawer';
import { OperationsSection } from './OperationsSection';
import type {
  ComponentCosting,
  MaterialSearchHit,
  OperationOut,
  OperationUpdateBody,
  ProcessOut,
  QuoteSummary,
} from './types';

export function EstimatingPage() {
  const { quoteId } = useParams<{ quoteId: string }>();
  const { t, i18n } = useTranslation();
  const api = useEstimatingApi();
  const canEdit = useHasPermission('quote_edit');

  const [quote, setQuote] = useState<QuoteSummary | null>(null);
  const [itemIndex, setItemIndex] = useState(0);
  const [costing, setCosting] = useState<ComponentCosting | null>(null);
  const [processes, setProcesses] = useState<ProcessOut[]>([]);
  const [material, setMaterial] = useState<MaterialSearchHit | null>(null);
  const [drawerOpId, setDrawerOpId] = useState<string | null>(null);
  const [changingProcess, setChangingProcess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const componentId = quote?.items[itemIndex]?.root_component_id ?? null;

  const fail = useCallback((e: unknown) => {
    setError(e instanceof ApiError ? e.message : String(e));
  }, []);

  useEffect(() => {
    if (!quoteId) return;
    api.getQuote(quoteId).then(setQuote).catch(fail);
    api.listProcesses().then(setProcesses).catch(fail);
  }, [api, quoteId, fail]);

  useEffect(() => {
    if (!componentId) return;
    api.getCosting(componentId).then(setCosting).catch(fail);
  }, [api, componentId, fail]);

  const formatMoney = useCallback(
    (value: string | null): string => {
      if (value == null) return '—';
      const amount = Number(value);
      if (Number.isNaN(amount)) return value;
      return new Intl.NumberFormat(i18n.language === 'de' ? 'de-DE' : 'en-IE', {
        style: 'currency',
        currency: quote?.currency ?? 'EUR',
      }).format(amount);
    },
    [i18n.language, quote?.currency],
  );

  const apply = useCallback(
    (next: Promise<ComponentCosting>) => {
      setError(null);
      next.then(setCosting).catch(fail);
    },
    [fail],
  );

  const pickMaterial = (materialId: string) => {
    if (componentId) apply(api.setComponentMaterial(componentId, materialId));
  };

  // Keep the selected material chip (name + path) in sync with the assignment.
  useEffect(() => {
    if (costing?.material_id == null) {
      setMaterial(null);
      return;
    }
    if (material?.id === costing.material_id) return;
    // The tree read is cheap at catalog scale and gives us name + path.
    api
      .materialTree()
      .then((tree) => {
        for (const cls of tree) {
          for (const family of cls.families) {
            const hit = family.materials.find((m) => m.id === costing.material_id);
            if (hit) {
              setMaterial({
                ...hit,
                class_name: cls.name,
                family_name: family.name,
                path: `${cls.name} / ${family.name} / ${hit.display_name}`,
              });
              return;
            }
          }
        }
        setMaterial(null);
      })
      .catch(() => setMaterial(null));
  }, [api, costing?.material_id, material?.id]);

  const moveOperation = (operationId: string, direction: -1 | 1) => {
    if (!costing || !componentId) return;
    const ordered = [...costing.operations].sort((a, b) => a.position - b.position);
    const index = ordered.findIndex((op) => op.id === operationId);
    if (index < 0) return;
    const category = ordered[index].category;
    // Swap with the adjacent row OF THE SAME CATEGORY (each section reorders
    // within itself); the full id list is what the API takes.
    let neighbor = index + direction;
    while (neighbor >= 0 && neighbor < ordered.length && ordered[neighbor].category !== category) {
      neighbor += direction;
    }
    if (neighbor < 0 || neighbor >= ordered.length) return;
    [ordered[index], ordered[neighbor]] = [ordered[neighbor], ordered[index]];
    apply(
      api.reorderOperations(
        componentId,
        ordered.map((op) => op.id),
      ),
    );
  };

  const drawerOp: OperationOut | null =
    (drawerOpId && costing?.operations.find((op) => op.id === drawerOpId)) || null;

  if (!quoteId) return null;
  if (!quote) {
    return <main className="est-page">{error ?? t('estimating.loading')}</main>;
  }

  const currentProcess = processes.find((p) => p.id === costing?.process_id) ?? null;
  const editable = canEdit && quote.status === 'draft';

  return (
    <main className="est-page">
      <header className="est-header">
        <h2>
          {t('estimating.title', { number: quote.number })}
        </h2>
        {quote.items.length > 1 && (
          <label>
            {t('estimating.line_item')}
            <select
              value={itemIndex}
              onChange={(e) => {
                setItemIndex(Number(e.target.value));
                setDrawerOpId(null);
              }}
            >
              {quote.items.map((item, index) => (
                <option key={item.id} value={index}>
                  {t('estimating.item_option', { position: item.position })}
                </option>
              ))}
            </select>
          </label>
        )}
        <div className="est-assignments">
          <span className="est-field-label">{t('estimating.process')}</span>
          <span>{currentProcess?.name ?? t('estimating.no_process')}</span>
          <button type="button" onClick={() => setChangingProcess(true)} disabled={!editable}>
            {t('estimating.change_process')}
          </button>
          <MaterialPicker
            selected={material}
            selectedPath={material?.path ?? null}
            search={(q) => api.searchMaterials(q)}
            loadTree={() => api.materialTree()}
            onPick={pickMaterial}
            onClear={() => componentId && apply(api.setComponentMaterial(componentId, null))}
            onEdit={async (materialId, body) => {
              await api.updateMaterial(materialId, body);
              setMaterial(null); // re-resolve (path/name may have changed)
            }}
            disabled={!editable}
          />
        </div>
      </header>

      {error && <p className="est-error" role="alert">{error}</p>}

      {costing && (
        <>
          <OperationsSection
            title={t('estimating.materials')}
            addLabel={t('estimating.add_material_operation')}
            category="material"
            operations={costing.operations}
            quantities={costing.quantities}
            formatMoney={formatMoney}
            searchDefs={(q) => api.listOperationDefs(q)}
            onAddFromDef={(defId) =>
              componentId && apply(api.addOperation(componentId, { operation_def_id: defId }))
            }
            onAddInline={(name) =>
              componentId &&
              apply(api.addOperation(componentId, { name, category: 'material' }))
            }
            onOpen={(op) => setDrawerOpId(op.id)}
            onDuplicate={(id) => apply(api.duplicateOperation(id))}
            onRemove={(id) => {
              setError(null);
              api
                .removeOperation(id)
                .then(() => (componentId ? api.getCosting(componentId).then(setCosting) : null))
                .catch(fail);
            }}
            onMove={moveOperation}
            disabled={!editable}
          />
          <OperationsSection
            title={t('estimating.operations')}
            addLabel={t('estimating.add_operation')}
            category="operation"
            operations={costing.operations}
            quantities={costing.quantities}
            formatMoney={formatMoney}
            searchDefs={(q) => api.listOperationDefs(q)}
            onAddFromDef={(defId) =>
              componentId && apply(api.addOperation(componentId, { operation_def_id: defId }))
            }
            onAddInline={(name) =>
              componentId && apply(api.addOperation(componentId, { name }))
            }
            onOpen={(op) => setDrawerOpId(op.id)}
            onDuplicate={(id) => apply(api.duplicateOperation(id))}
            onRemove={(id) => {
              setError(null);
              api
                .removeOperation(id)
                .then(() => (componentId ? api.getCosting(componentId).then(setCosting) : null))
                .catch(fail);
            }}
            onMove={moveOperation}
            disabled={!editable}
          />

          <section className="est-section">
            <h3>{t('estimating.rollup_title')}</h3>
            <table className="est-table">
              <thead>
                <tr>
                  <th>{t('estimating.rollup_category')}</th>
                  {costing.buckets.map((bucket) => (
                    <th key={bucket.quantity} className="est-num">
                      {bucket.quantity}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{t('estimating.rollup_material')}</td>
                  {costing.buckets.map((bucket) => (
                    <td key={bucket.quantity} className="est-num">
                      {formatMoney(bucket.material_total)}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>{t('estimating.rollup_inside')}</td>
                  {costing.buckets.map((bucket) => (
                    <td key={bucket.quantity} className="est-num">
                      {formatMoney(bucket.inside_total)}
                    </td>
                  ))}
                </tr>
                <tr>
                  <td>{t('estimating.rollup_outside')}</td>
                  {costing.buckets.map((bucket) => (
                    <td key={bucket.quantity} className="est-num">
                      {formatMoney(bucket.outside_total)}
                    </td>
                  ))}
                </tr>
              </tbody>
              <tfoot>
                <tr>
                  <td>{t('estimating.rollup_total')}</td>
                  {costing.buckets.map((bucket) => (
                    <td key={bucket.quantity} className="est-num">
                      {formatMoney(bucket.total)}
                      {bucket.has_unpriced_rows && (
                        <span
                          className="est-warning"
                          title={t('estimating.unpriced_rows_hint')}
                        >
                          {' '}!
                        </span>
                      )}
                    </td>
                  ))}
                </tr>
              </tfoot>
            </table>
          </section>
        </>
      )}

      {drawerOp && (
        <OperationDrawer
          key={drawerOp.id}
          operation={drawerOp}
          formatMoney={formatMoney}
          onSave={(body: OperationUpdateBody) => apply(api.updateOperation(drawerOp.id, body))}
          onCellOverride={(quantity, manualCost) =>
            apply(api.setCellOverride(drawerOp.id, quantity, manualCost))
          }
          onClose={() => setDrawerOpId(null)}
          disabled={!editable}
        />
      )}
      {changingProcess && (
        <ChangeProcessModal
          processes={processes}
          currentProcessId={costing?.process_id ?? null}
          onCommit={(processId, keep) => {
            setChangingProcess(false);
            if (componentId) apply(api.setComponentProcess(componentId, processId, keep));
          }}
          onClose={() => setChangingProcess(false)}
        />
      )}
    </main>
  );
}
