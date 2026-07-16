/**
 * Part-estimating view, M1.7 cut (spec #partview): for a quote's line item —
 * header assignments (Process + Change Process, Material nested picker + Edit
 * Material Properties + clear), the Materials and Operations sections with
 * per-quantity cost columns, the operation drawer (Calculated vs Override), and
 * the roll-up input summary (#costing: Raw Material / Inside / Outside per
 * break). Route: /quotes/:quoteId — the M1.4 quote detail screen proper arrives
 * with later blocks; this page is the Materials & Operations slice.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { useConfigureApi } from '../configure/api';
import { PartMatchesChip } from '../parts/MatchingParts';
import {
  RULE_SEED_DOCUMENT_PATHS,
  type RuleSuggestionPayload,
  suggestionSeed,
  useRuleSuggestApi,
} from '../review/api';
import { CreateRuleModal, type NewRule } from '../review/CreateRuleModal';
import { useHasPermission } from '../session/session';
import { AddOnsSection } from './AddOnsSection';
import { CommunicationsSection } from './CommunicationsSection';
import { BulkCreateDialog } from './BulkCreateDialog';
import { useEstimatingApi } from './api';
import { ChangeProcessModal } from './ChangeProcessModal';
import { LeadTimesSection } from './LeadTimesSection';
import { MaterialPicker } from './MaterialPicker';
import { OperationDrawer } from './OperationDrawer';
import { ReviewItemsPanel } from '../review/ReviewItemsPanel';
import { OperationsSection } from './OperationsSection';
import { PricingSection } from './PricingSection';
import { QuoteTotalsPanel } from './QuoteTotalsPanel';
import type {
  BulkCreatePrefill,
  ComponentCosting,
  MaterialSearchHit,
  NestingOverview,
  OperationOut,
  OperationUpdateBody,
  PricingSummary,
  ProcessOut,
  QuoteSummary,
  QuoteTotals,
} from './types';

export function EstimatingPage() {
  const { quoteId } = useParams<{ quoteId: string }>();
  const { t, i18n } = useTranslation();
  const api = useEstimatingApi();
  const suggestApi = useRuleSuggestApi();
  const configureApi = useConfigureApi();
  const canEdit = useHasPermission('quote_edit');

  const [quote, setQuote] = useState<QuoteSummary | null>(null);
  const [itemIndex, setItemIndex] = useState(0);
  const [costing, setCosting] = useState<ComponentCosting | null>(null);
  const [pricing, setPricing] = useState<PricingSummary | null>(null);
  const [totals, setTotals] = useState<QuoteTotals | null>(null);
  const [processes, setProcesses] = useState<ProcessOut[]>([]);
  const [material, setMaterial] = useState<MaterialSearchHit | null>(null);
  const [drawerOpId, setDrawerOpId] = useState<string | null>(null);
  const [changingProcess, setChangingProcess] = useState(false);
  const [ruleSuggestion, setRuleSuggestion] = useState<RuleSuggestionPayload | null>(null);
  const [seedingRule, setSeedingRule] = useState(false);
  const [bulkCreating, setBulkCreating] = useState(false);
  const [bulkPrefill, setBulkPrefill] = useState<BulkCreatePrefill | null>(null);
  const [nesting, setNesting] = useState<NestingOverview | null>(null);
  const [error, setError] = useState<string | null>(null);

  const componentId = quote?.items[itemIndex]?.root_component_id ?? null;
  const partId = quote?.items[itemIndex]?.part_id ?? null;

  const fail = useCallback((e: unknown) => {
    setError(e instanceof ApiError ? e.message : String(e));
  }, []);

  useEffect(() => {
    if (!quoteId) return;
    api.getQuote(quoteId).then(setQuote).catch(fail);
    api.listProcesses().then(setProcesses).catch(fail);
    // Lens suggestion availability drives the entry link's purple hint
    // ("Line items found in <eml>" — DemoB); absence is not an error.
    api
      .getBulkCreatePrefill(quoteId)
      .then(setBulkPrefill)
      .catch(() => setBulkPrefill(null));
    // M4.3 — nest eligibility for the banner + NESTABLE/NESTED badge; a quote
    // with no sheet-metal components just gets an empty overview.
    api
      .getNestingOverview(quoteId)
      .then(setNesting)
      .catch(() => setNesting(null));
  }, [api, quoteId, fail]);

  const loadPricing = useCallback(() => {
    if (!componentId) return;
    api.getPricing(componentId).then(setPricing).catch(fail);
    // quote-level VAT totals move with every price/add-on change
    if (quoteId) api.getQuoteTotals(quoteId).then(setTotals).catch(fail);
  }, [api, componentId, quoteId, fail]);

  // Guards the async rule-suggestion probe against a line-item switch (M3.10):
  // a probe fired for component A must not paint A's chip after the user moved
  // to component B.
  const activeComponentRef = useRef<string | null>(null);

  useEffect(() => {
    if (!componentId) return;
    // Switching line items: drop any chip from the previous component.
    activeComponentRef.current = componentId;
    setRuleSuggestion(null);
    api.getCosting(componentId).then(setCosting).catch(fail);
    loadPricing();
  }, [api, componentId, fail, loadPricing]);

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
      next
        .then((costingNext) => {
          setCosting(costingNext);
          loadPricing(); // pricing always follows costs (M1.10)
        })
        .catch(fail);
    },
    [fail, loadPricing],
  );

  // M3.10 — after a *manual* operation add, probe for a rule-suggestion pattern
  // (non-blocking; a miss or an error just leaves the chip hidden). The chip is
  // transient (this render), separate from the persisted dashboard strip.
  const applyAdd = useCallback(
    (next: Promise<ComponentCosting>) => {
      setError(null);
      next
        .then((costingNext) => {
          setCosting(costingNext);
          loadPricing();
          const probed = componentId;
          if (probed) {
            suggestApi
              .getRuleSuggestion(probed)
              .then((r) => {
                // Ignore a stale probe if the user has since switched line items.
                if (activeComponentRef.current === probed) setRuleSuggestion(r.suggestion);
              })
              .catch(() => undefined);
          }
        })
        .catch(fail);
    },
    [componentId, loadPricing, fail, suggestApi],
  );

  // A pricing-side mutation moves prices AND the costing view's custom rows.
  const applyPricing = useCallback(
    (next: Promise<unknown>) => {
      setError(null);
      next.then(loadPricing).catch(fail);
    },
    [fail, loadPricing],
  );

  // Stable reference — KalkSection's report effect depends on it, so an inline
  // arrow would refetch the report on every unrelated page re-render.
  const loadKalkReport = useCallback(
    () => api.getKalkReport(drawerOpId ?? ''),
    [api, drawerOpId],
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

  // quantity → make quantity for the Yield / Make Quantity footer rows
  const makeQuantities: Record<number, number> = Object.fromEntries(
    (quote.items[itemIndex]?.quantities ?? []).map((q) => [q.quantity, q.make_quantity]),
  );

  const refreshPricing = () => {
    setError(null);
    api
      .refreshPricing(quoteId)
      .then(() => {
        if (componentId) api.getCosting(componentId).then(setCosting).catch(fail);
        loadPricing();
      })
      .catch(fail);
  };

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
        {partId && (
          <PartMatchesChip
            key={partId}
            partId={partId}
            componentId={componentId ?? undefined}
            editable={editable}
            onImported={() => {
              if (componentId) {
                api.getCosting(componentId).then(setCosting).catch(fail);
                loadPricing(); // pricing always follows costs (M1.10)
              }
            }}
          />
        )}
        <span className="bulk-create-entry">
          <button
            type="button"
            className={
              bulkPrefill?.status === 'completed' &&
              bulkPrefill.rows.length > 0 &&
              quote.items.length === 0
                ? 'bulk-create-open has-suggestions'
                : 'bulk-create-open'
            }
            onClick={() => setBulkCreating(true)}
            disabled={!editable}
          >
            {t('bulk_create.open_button')}
          </button>
          {bulkPrefill?.status === 'completed' &&
            bulkPrefill.rows.length > 0 &&
            bulkPrefill.found_in &&
            // The purple hint is an INTAKE affordance — once line items
            // exist, its suggestions are consumed and it must not keep
            // advertising them (CodeRabbit minor).
            quote.items.length === 0 && (
              <span className="bulk-create-hint">
                {t('bulk_create.items_found_in', { file: bulkPrefill.found_in })}
              </span>
            )}
        </span>
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

      {quote.missing_rates_item_count > 0 && (
        <p className="est-warning-banner" role="status">
          {t('estimating.missing_rates_banner', { count: quote.missing_rates_item_count })}{' '}
          <Link to="/configure/operations">{t('estimating.configure_rates_link')}</Link>
        </p>
      )}

      {ruleSuggestion && (
        <div className="rule-suggest-chip" role="status" data-testid="rule-suggest-chip">
          <span>{ruleSuggestion.sentence}</span>
          <div className="rule-suggest-chip-buttons">
            <button type="button" onClick={() => setSeedingRule(true)}>
              {t('rule_suggest.create_rule')}
            </button>
            <button
              type="button"
              onClick={() => {
                // Dismiss the *persisted* suggestion so it doesn't re-nag on the
                // dashboard strip, then hide the chip.
                const id = ruleSuggestion.suggested_action_id;
                if (id) suggestApi.dismissSuggestedAction(id).catch(() => undefined);
                setRuleSuggestion(null);
              }}
            >
              {t('rule_suggest.dismiss')}
            </button>
          </div>
        </div>
      )}
      {seedingRule && ruleSuggestion && (
        <CreateRuleModal
          documentPaths={RULE_SEED_DOCUMENT_PATHS}
          suggestion={suggestionSeed(ruleSuggestion)}
          onCreate={async (rule: NewRule) => {
            // No rule until this call — the human clicked CREATE RULE.
            await configureApi.importRules(JSON.stringify([rule]));
            // Consume the persisted suggestion so the dashboard strip can't
            // author a duplicate rule from the same pattern.
            const id = ruleSuggestion.suggested_action_id;
            if (id) await suggestApi.dismissSuggestedAction(id).catch(() => undefined);
            setSeedingRule(false);
            setRuleSuggestion(null);
          }}
          onClose={() => setSeedingRule(false)}
        />
      )}

      {/* M4.3 (DemoA/12): the nest-eligibility banner on a sheet-metal part.
          Warnings detail stays M4.7 — this is the eligible/nested state only. */}
      {(() => {
        const nestRow = nesting?.sheet_metal.find((r) => r.component_id === componentId);
        if (!nestRow || (!nestRow.eligible && !nestRow.nest_id)) return null;
        return (
          <p className="nesting-banner" role="status">
            {nestRow.nest_id ? (
              <>
                <span className="nesting-badge nested">{t('nesting.badge_nested')}</span>{' '}
                {t('nesting.banner_nested', { label: nestRow.nest_label ?? '' })}
              </>
            ) : (
              <>
                <span className="nesting-badge">{t('nesting.badge_nestable')}</span>{' '}
                {t('nesting.banner_eligible')}
              </>
            )}{' '}
            <Link to={`/quotes/${quoteId}/nesting`}>{t('nesting.open_module')}</Link>
          </p>
        );
      })()}

      {costing && (
        <>
          <OperationsSection
            sectionId="materials"
            title={t('estimating.materials')}
            addLabel={t('estimating.add_material_operation')}
            summaryLabel={t('estimating.material_summary')}
            category="material"
            operations={costing.operations}
            quantities={costing.quantities}
            formatMoney={formatMoney}
            searchDefs={(q) => api.listOperationDefs(q)}
            onAddFromDef={(defId) =>
              componentId && applyAdd(api.addOperation(componentId, { operation_def_id: defId }))
            }
            onAddInline={(name) =>
              componentId &&
              applyAdd(api.addOperation(componentId, { name, category: 'material' }))
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
            sectionId="operations"
            title={t('estimating.operations')}
            addLabel={t('estimating.add_operation')}
            summaryLabel={t('estimating.operation_summary')}
            category="operation"
            operations={costing.operations}
            quantities={costing.quantities}
            makeQuantities={makeQuantities}
            formatMoney={formatMoney}
            searchDefs={(q) => api.listOperationDefs(q)}
            onAddFromDef={(defId) =>
              componentId && applyAdd(api.addOperation(componentId, { operation_def_id: defId }))
            }
            onAddInline={(name) =>
              componentId && applyAdd(api.addOperation(componentId, { name }))
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

          {/* M3.8: the line-item Review Items panel. A resolution can mutate the
              router (ADD_OPERATION / SET_PROCESS), so refetch the costing it
              just changed rather than leaving a stale grid on screen. */}
          {componentId && (
            <ReviewItemsPanel
              componentId={componentId}
              onResolved={() => {
                api.getCosting(componentId).then(setCosting).catch(fail);
                loadPricing();
              }}
            />
          )}

          {pricing && (
            <PricingSection
              pricing={pricing}
              formatMoney={formatMoney}
              editable={editable}
              onAddItem={(body) =>
                componentId && applyPricing(api.addPricingItem(componentId, body))
              }
              onUpdateItem={(id, body) => applyPricing(api.updatePricingItem(id, body))}
              onRemoveItem={(id) => applyPricing(api.removePricingItem(id))}
              onReorderItems={(ids) =>
                componentId && applyPricing(api.reorderPricingItems(componentId, ids))
              }
              onItemPctOverride={(id, quantity, manualPct) =>
                applyPricing(api.setPricingItemPct(id, quantity, manualPct))
              }
              onAddDiscount={(body) =>
                componentId && applyPricing(api.addDiscount(componentId, body))
              }
              onRemoveDiscount={(id) => applyPricing(api.removeDiscount(id))}
              onDiscountPctOverride={(id, quantity, manualPct) =>
                applyPricing(api.setDiscountPct(id, quantity, manualPct))
              }
              onUnitPriceOverride={(quantity, manualUnitPrice) =>
                componentId &&
                applyPricing(api.setUnitPriceOverride(componentId, quantity, manualUnitPrice))
              }
              onRefreshPricing={refreshPricing}
              loadItemDefs={api.listPricingItemDefs}
              loadDiscountDefs={api.listDiscountDefs}
              onKalkCheck={api.kalkCheck}
            />
          )}

          {pricing && (
            <AddOnsSection
              pricing={pricing}
              formatMoney={formatMoney}
              editable={editable}
              loadDefs={api.listAddOnDefs}
              onAdd={(body) => componentId && applyPricing(api.addAddOn(componentId, body))}
              onRemove={(id) => applyPricing(api.removeAddOn(id))}
              onToggleRequired={(id, manualIsRequired) =>
                applyPricing(api.updateAddOn(id, { manual_is_required: manualIsRequired }))
              }
              onPriceOverride={(id, quantity, manualPrice) =>
                applyPricing(api.setAddOnPrice(id, quantity, manualPrice))
              }
            />
          )}

          {pricing && (
            <LeadTimesSection
              pricing={pricing}
              formatMoney={formatMoney}
              editable={editable}
              onLeadTimeOverride={(quantity, manualDays) =>
                componentId && applyPricing(api.setLeadTime(componentId, quantity, manualDays))
              }
              onSetExpediteOptions={(options) =>
                componentId && applyPricing(api.setExpediteOptions(componentId, options))
              }
              onApplyToAll={(standardDays, tiers) =>
                applyPricing(
                  api.applyLeadTimesToAll(quoteId, {
                    standard_lead_time_days: standardDays,
                    tiers,
                  }),
                )
              }
            />
          )}

          {totals && <QuoteTotalsPanel totals={totals} />}

          {/* Unified communications timeline (M3.5) — email round-trips on
              this quote; send box needs quote_edit (canEdit). */}
          {quoteId && <CommunicationsSection quoteId={quoteId} canSend={canEdit} />}
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
          onKalkCheck={api.kalkCheck}
          loadKalkReport={loadKalkReport}
          onSaveOverrides={(overrides) =>
            apply(api.setVariableOverrides(drawerOp.id, overrides))
          }
        />
      )}
      {bulkCreating && (
        <BulkCreateDialog
          quoteId={quoteId}
          getPrefill={api.getBulkCreatePrefill}
          create={api.bulkCreateLineItems}
          onCreated={(next) => {
            setBulkCreating(false);
            setQuote(next);
            // Newly created items may already carry files/quantities; pricing
            // and costing follow the (possibly new) selected item. The header
            // hint refreshes too — its suggestions were just consumed.
            if (quoteId) {
              api.getQuoteTotals(quoteId).then(setTotals).catch(fail);
              api
                .getBulkCreatePrefill(quoteId)
                .then(setBulkPrefill)
                .catch(() => setBulkPrefill(null));
              // new line items may be nest-eligible — refresh the banner data
              api
                .getNestingOverview(quoteId)
                .then(setNesting)
                .catch(() => setNesting(null));
            }
          }}
          onClose={() => setBulkCreating(false)}
        />
      )}
      {changingProcess && (
        <ChangeProcessModal
          processes={processes}
          currentProcessId={costing?.process_id ?? null}
          currentMaterial={material}
          searchMaterials={(q) => api.searchMaterials(q)}
          onCommit={(processId, keep, materialId) => {
            setChangingProcess(false);
            if (!componentId) return;
            apply(
              api
                .setComponentProcess(componentId, processId, keep)
                .then((next) =>
                  materialId !== undefined
                    ? api.setComponentMaterial(componentId, materialId)
                    : next,
                ),
            );
          }}
          onClose={() => setChangingProcess(false)}
        />
      )}
    </main>
  );
}
