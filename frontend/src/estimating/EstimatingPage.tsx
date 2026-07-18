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
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';

import { ApiError } from '../api/client';
import { useBomApi } from '../bom/api';
import { BomBuilderModal } from '../bom/BomBuilderModal';
import type { BomStatus } from '../bom/types';
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
import { SendQuoteComposer } from './SendQuoteComposer';
import { LeadTimesSection } from './LeadTimesSection';
import { LineItemActionsMenu } from './LineItemActionsMenu';
import { LineItemSidebar } from './LineItemSidebar';
import { MaterialPicker } from './MaterialPicker';
import { RequestedFinishes } from './RequestedFinishes';
import { OperationDrawer } from './OperationDrawer';
import { ReviewItemsPanel } from '../review/ReviewItemsPanel';
import { OperationsSection } from './OperationsSection';
import { PricingSection } from './PricingSection';
import { QuoteTotalsPanel } from './QuoteTotalsPanel';
import { RequoteDiffPanel } from './RequoteDiffPanel';
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
  RequoteDiffEntry,
} from './types';

export function EstimatingPage() {
  // M5.0 #partview — the spec route is /quotes/edit/:id/:lineItemId (a left sidebar
  // picks the item). `/quotes/edit/:id` (no item) forwards to the first one below.
  const { id: quoteId, lineItemId } = useParams<{ id: string; lineItemId?: string }>();
  const navigate = useNavigate();
  const { t, i18n } = useTranslation();
  const api = useEstimatingApi();
  const suggestApi = useRuleSuggestApi();
  const configureApi = useConfigureApi();
  const canEdit = useHasPermission('quote_edit');

  const [quote, setQuote] = useState<QuoteSummary | null>(null);
  const [costing, setCosting] = useState<ComponentCosting | null>(null);
  const [pricing, setPricing] = useState<PricingSummary | null>(null);
  const [totals, setTotals] = useState<QuoteTotals | null>(null);
  const [processes, setProcesses] = useState<ProcessOut[]>([]);
  const [material, setMaterial] = useState<MaterialSearchHit | null>(null);
  const [drawerOpId, setDrawerOpId] = useState<string | null>(null);
  const [changingProcess, setChangingProcess] = useState(false);
  const [sendingQuote, setSendingQuote] = useState(false);
  const [ruleSuggestion, setRuleSuggestion] = useState<RuleSuggestionPayload | null>(null);
  const [seedingRule, setSeedingRule] = useState(false);
  const [bulkCreating, setBulkCreating] = useState(false);
  const [bulkPrefill, setBulkPrefill] = useState<BulkCreatePrefill | null>(null);
  const [nesting, setNesting] = useState<NestingOverview | null>(null);
  const [requoteEntries, setRequoteEntries] = useState<RequoteDiffEntry[]>([]);
  const [requoteBusy, setRequoteBusy] = useState(false);
  const [bomStatus, setBomStatus] = useState<BomStatus | null>(null);
  const [bomBuilderOpen, setBomBuilderOpen] = useState(false);
  const [bomPublishedToast, setBomPublishedToast] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The active line item is derived SYNCHRONOUSLY from the URL (M5.0) — never a
  // state+effect, so a deep link to a non-first item never briefly loads item 0's
  // costing (the CodeRabbit race). Falls back to 0 while the quote loads / before
  // the forward-to-first effect below fires.
  const resolvedIndex = quote ? quote.items.findIndex((i) => i.id === lineItemId) : -1;
  const itemIndex = resolvedIndex >= 0 ? resolvedIndex : 0;

  const componentId = quote?.items[itemIndex]?.root_component_id ?? null;
  const partId = quote?.items[itemIndex]?.part_id ?? null;
  const quoteItemId = quote?.items[itemIndex]?.id ?? null;

  // If the URL lacks a valid lineItemId but the quote has items, forward to the
  // first — so `/quotes/edit/:id` and the old-route redirect both land on a real item.
  useEffect(() => {
    if (!quote || !quoteId || quote.items.length === 0) return;
    if (quote.items.findIndex((i) => i.id === lineItemId) === -1) {
      navigate(`/quotes/edit/${quoteId}/${quote.items[0].id}`, { replace: true });
    }
  }, [quote, quoteId, lineItemId, navigate]);

  // Switching line items closes any open operation drawer (it belongs to the
  // previous component).
  useEffect(() => {
    setDrawerOpId(null);
  }, [lineItemId]);

  const fail = useCallback((e: unknown) => {
    setError(e instanceof ApiError ? e.message : String(e));
  }, []);

  const bomApi = useBomApi();

  // M4.9 — the "BOM table found … OPEN IN BOM BUILDER" banner state per line
  // item; a part without findings or children simply shows no banner.
  useEffect(() => {
    let cancelled = false;
    setBomStatus(null);
    setBomPublishedToast(false);
    if (!quoteItemId) return;
    bomApi
      .getBomStatus(quoteItemId)
      .then((bomState) => {
        if (!cancelled) setBomStatus(bomState);
      })
      .catch(() => {
        if (!cancelled) setBomStatus(null);
      });
    return () => {
      cancelled = true;
    };
  }, [bomApi, quoteItemId]);

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
    // M4.12 — requote diff entries for the "Previous quote found" banner;
    // absence (no match / task not run yet) is not an error.
    api
      .getRequoteDiff(quoteId)
      .then((r) => setRequoteEntries(r.entries))
      .catch(() => setRequoteEntries([]));
  }, [api, quoteId, fail]);

  // Guards every item-scoped async load against a line-item switch (M3.10/M5.0):
  // a response for component A must never paint after the user moved to B.
  const activeComponentRef = useRef<string | null>(null);

  const loadPricing = useCallback(() => {
    if (!componentId) return;
    const cid = componentId;
    api
      .getPricing(cid)
      .then((p) => {
        if (activeComponentRef.current === cid) setPricing(p);
      })
      .catch(fail);
    // quote-level VAT totals move with every price/add-on change
    if (quoteId)
      api
        .getQuoteTotals(quoteId)
        .then((tot) => {
          if (activeComponentRef.current === cid) setTotals(tot);
        })
        .catch(fail);
  }, [api, componentId, quoteId, fail]);

  // M4.12 — the explicit three-choice requote gate. Every choice is recorded
  // for the audit trail; ONLY the import button touches the router.
  const recordRequoteChoice = useCallback(
    (entry: RequoteDiffEntry, choice: 'import_router' | 'review' | 'start_fresh') => {
      if (!quoteId) return Promise.resolve();
      setRequoteBusy(true);
      return api
        .postRequoteChoice(quoteId, entry.part_id, choice)
        .then((r) => setRequoteEntries(r.entries))
        .catch(fail)
        .finally(() => setRequoteBusy(false));
    },
    [api, quoteId, fail],
  );

  const importRequoteRouter = useCallback(
    (entry: RequoteDiffEntry) => {
      if (!quoteId) return;
      setRequoteBusy(true);
      api
        .importRouter(entry.target_component_id, entry.matched.component_id)
        .then(() => {
          // The import succeeded: reflect the copied router immediately and
          // dismiss the panel optimistically — the audit POST below must not
          // gate what already happened server-side.
          if (componentId) {
            api.getCosting(componentId).then(setCosting).catch(fail);
            loadPricing();
          }
          setRequoteEntries((prev) =>
            prev.map((e) =>
              e.part_id === entry.part_id
                ? { ...e, choice: { choice: 'import_router' as const, at: new Date().toISOString() } }
                : e,
            ),
          );
          return api.postRequoteChoice(quoteId, entry.part_id, 'import_router');
        })
        .then((r) => setRequoteEntries(r.entries))
        .catch(fail)
        .finally(() => setRequoteBusy(false));
    },
    [api, quoteId, componentId, fail, loadPricing],
  );

  // M4.13 — the two explicit-accept assembly paths (atomic router + pricing
  // import server-side; Accept All re-checked and undo-armed there) and the
  // 60-second undo. Costing + pricing reload after each, since both move.
  const assemblyAct = useCallback(
    (entry: RequoteDiffEntry, action: 'accept_all' | 'review' | 'undo') => {
      if (!quoteId) return;
      setRequoteBusy(true);
      // The import mutates the entry's own component — refresh THAT one, and
      // re-check it is still the active line item before every state write
      // (the M3.10 pattern): a switch mid-request must not let component A's
      // costing paint component B's view.
      const target = entry.target_component_id;
      const call =
        action === 'undo'
          ? api.assemblyUndo(quoteId, entry.part_id)
          : api.assemblyImport(quoteId, entry.part_id, action);
      call
        .then((r) => {
          setRequoteEntries(r.entries);
          if (activeComponentRef.current !== target) return;
          api
            .getCosting(target)
            .then((c) => {
              if (activeComponentRef.current === target) setCosting(c);
            })
            .catch(fail);
          loadPricing();
        })
        .catch(fail)
        .finally(() => setRequoteBusy(false));
    },
    [api, quoteId, fail, loadPricing],
  );

  // Switching line items drops the previous component's item-scoped state so the
  // old item's numbers never linger under the new one. Keyed on componentId ALONE
  // (not the load deps) so it fires once per real switch — never on an unrelated
  // re-render, which would blank a freshly-loaded costing.
  useEffect(() => {
    setCosting(null);
    setPricing(null);
    setTotals(null);
    setRuleSuggestion(null);
  }, [componentId]);

  useEffect(() => {
    if (!componentId) return;
    const cid = componentId;
    activeComponentRef.current = cid;
    api
      .getCosting(cid)
      .then((c) => {
        if (activeComponentRef.current === cid) setCosting(c);
      })
      .catch(fail);
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

  // M5.0 — sidebar navigation + line-item costing-inputs actions.
  const selectItem = (itemId: string) => navigate(`/quotes/edit/${quoteId}/${itemId}`);

  const addLineItem = () => {
    setError(null);
    api
      .addLineItem(quoteId)
      .then((next) => {
        setQuote(next);
        const added = next.items[next.items.length - 1];
        if (added) navigate(`/quotes/edit/${quoteId}/${added.id}`);
      })
      .catch(fail);
  };

  const attachFinish = (defId: string) => {
    if (componentId) apply(api.addOperation(componentId, { operation_def_id: defId }));
  };

  const removeFinish = (operationId: string) => {
    setError(null);
    api
      .removeOperation(operationId)
      .then(() => {
        if (componentId) api.getCosting(componentId).then(setCosting).catch(fail);
        loadPricing();
      })
      .catch(fail);
  };

  const setPriority = (priority: number | null) => {
    if (!quoteItemId) return;
    setError(null);
    api.setLineItemPriority(quoteId, quoteItemId, priority).then(setQuote).catch(fail);
  };

  const activeItem = quote.items[itemIndex] ?? null;

  return (
    <div className="est-layout">
      <LineItemSidebar
        quote={quote}
        activeItemId={quoteItemId}
        editable={editable}
        onSelect={selectItem}
        onAddItem={addLineItem}
      />
      <main className="est-page">
      <header className="est-header">
        <Link className="est-return-link" to="/quotes">
          {t('estimating.return_to_quotes')}
        </Link>
        <h2>
          {t('estimating.title', { number: quote.number })}
        </h2>
        {canEdit && (
          <button
            type="button"
            className="est-send-quote"
            onClick={() => setSendingQuote(true)}
          >
            {t('sendComposer.send_quote')}
          </button>
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
          {componentId && (
            <RequestedFinishes
              operations={costing?.operations ?? []}
              loadFinishDefs={api.listFinishDefs}
              onAttach={attachFinish}
              onRemove={removeFinish}
              disabled={!editable}
            />
          )}
          {activeItem && (
            <LineItemActionsMenu
              priority={activeItem.priority}
              onSetPriority={setPriority}
              disabled={!editable}
            />
          )}
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

      {/* M4.9 (DemoD/12): the persistent BOM banner — a detected BOM table or a
          published BOM both open the builder; publish shows the success toast. */}
      {bomPublishedToast && (
        <p className="bom-check-ok" role="status">
          {t('bom.published_toast')}
        </p>
      )}
      {bomStatus && (bomStatus.suggestion || bomStatus.has_children || bomStatus.has_draft) && (
        <div className="bom-line-banner" role="status">
          <span className="bom-sparkle" aria-hidden="true">
            ✦
          </span>
          <span>
            {bomStatus.suggestion
              ? t('bom.banner_found', {
                  file: bomStatus.suggestion.filename,
                  page: bomStatus.suggestion.page ?? 1,
                })
              : t('bom.banner_edit')}
          </span>
          {canEdit && quote?.status === 'draft' && (
            <button
              type="button"
              className="bom-open-builder"
              onClick={() => setBomBuilderOpen(true)}
            >
              {t('bom.banner_open')}
            </button>
          )}
        </div>
      )}
      {bomBuilderOpen && quoteItemId && (
        <BomBuilderModal
          quoteItemId={quoteItemId}
          api={bomApi}
          onPublished={() => {
            setBomBuilderOpen(false);
            setBomPublishedToast(true);
            bomApi
              .getBomStatus(quoteItemId)
              .then(setBomStatus)
              .catch(() => undefined);
          }}
          onClose={() => setBomBuilderOpen(false)}
        />
      )}

      {/* M4.12 (spec #ai-requote-diff): "Previous quote found — see what
          changed". Visible until an explicit choice dismisses it; a recorded
          "review" keeps the panel available. */}
      {(() => {
        const entry = requoteEntries.find(
          (e) =>
            e.part_id === partId &&
            (e.choice === null ||
              e.choice.choice === 'review' ||
              // M4.13: an active import record keeps the panel up — it carries
              // the audit line and (for Accept All) the 60-second undo chip.
              (e.assembly != null && e.assembly.undone_at === null)),
        );
        if (!entry) return null;
        return (
          <RequoteDiffPanel
            entry={entry}
            busy={requoteBusy || !canEdit}
            onImport={() => importRequoteRouter(entry)}
            onReview={() => {
              if (entry.choice === null) void recordRequoteChoice(entry, 'review');
            }}
            onStartFresh={() => void recordRequoteChoice(entry, 'start_fresh')}
            onAcceptAll={() => assemblyAct(entry, 'accept_all')}
            onImportForReview={() => assemblyAct(entry, 'review')}
            onUndo={() => assemblyAct(entry, 'undo')}
          />
        );
      })()}

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
      {sendingQuote && (
        <SendQuoteComposer
          quoteId={quoteId}
          onClose={() => setSendingQuote(false)}
          onSent={() => {
            // Reflect the new Sent status on the quote header.
            api.getQuote(quoteId).then(setQuote).catch(fail);
          }}
        />
      )}
      </main>
    </div>
  );
}
