/**
 * Estimating API (M1.7) — component costing, material picker, processes and the
 * operation library, bound to the Clerk session token once (the `useQuotesApi`
 * pattern; tests mock this module wholesale).
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiFetch, type TokenGetter } from '../api/client';
import type {
  AddOnCreateBody,
  BulkCreatePrefill,
  BulkCreateRowBody,
  AddOnDefOut,
  ClassNode,
  ComponentCosting,
  DiscountCreateBody,
  DiscountDefLite,
  ExpediteTierBody,
  PricingItemCreateBody,
  PricingItemDefLite,
  PricingItemUpdateBody,
  PricingSummary,
  QuoteTotals,
  KalkCheckResult,
  KalkQtyReport,
  MaterialOut,
  MaterialSearchHit,
  MaterialUpdateBody,
  OperationCreateBody,
  OperationDefOut,
  OperationUpdateBody,
  ProcessOut,
  QuoteSummary,
  VariableOverrideValue,
} from './types';

export interface EstimatingApi {
  getQuote: (quoteId: string) => Promise<QuoteSummary>;
  getCosting: (componentId: string) => Promise<ComponentCosting>;
  materialTree: () => Promise<ClassNode[]>;
  searchMaterials: (q: string) => Promise<MaterialSearchHit[]>;
  updateMaterial: (materialId: string, body: MaterialUpdateBody) => Promise<MaterialOut>;
  listProcesses: () => Promise<ProcessOut[]>;
  listOperationDefs: (q: string) => Promise<OperationDefOut[]>;
  setComponentMaterial: (
    componentId: string,
    materialId: string | null,
  ) => Promise<ComponentCosting>;
  setComponentProcess: (
    componentId: string,
    processId: string | null,
    keepOperations: boolean,
  ) => Promise<ComponentCosting>;
  addOperation: (componentId: string, body: OperationCreateBody) => Promise<ComponentCosting>;
  updateOperation: (operationId: string, body: OperationUpdateBody) => Promise<ComponentCosting>;
  duplicateOperation: (operationId: string) => Promise<ComponentCosting>;
  removeOperation: (operationId: string) => Promise<void>;
  reorderOperations: (componentId: string, operationIds: string[]) => Promise<ComponentCosting>;
  setCellOverride: (
    operationId: string,
    quantity: number,
    manualCost: string | null,
  ) => Promise<ComponentCosting>;
  kalkCheck: (formula: string) => Promise<KalkCheckResult>;
  getKalkReport: (operationId: string) => Promise<KalkQtyReport[]>;
  setVariableOverrides: (
    operationId: string,
    overrides: Record<string, VariableOverrideValue>,
  ) => Promise<ComponentCosting>;
  getPricing: (componentId: string) => Promise<PricingSummary>;
  addPricingItem: (componentId: string, body: PricingItemCreateBody) => Promise<unknown>;
  updatePricingItem: (pricingItemId: string, body: PricingItemUpdateBody) => Promise<unknown>;
  reorderPricingItems: (componentId: string, pricingItemIds: string[]) => Promise<unknown>;
  listPricingItemDefs: () => Promise<PricingItemDefLite[]>;
  listDiscountDefs: () => Promise<DiscountDefLite[]>;
  removePricingItem: (pricingItemId: string) => Promise<void>;
  setPricingItemPct: (
    pricingItemId: string,
    quantity: number,
    manualPct: string | null,
  ) => Promise<unknown>;
  addDiscount: (componentId: string, body: DiscountCreateBody) => Promise<unknown>;
  removeDiscount: (discountId: string) => Promise<void>;
  setDiscountPct: (
    discountId: string,
    quantity: number,
    manualPct: string | null,
  ) => Promise<unknown>;
  setUnitPriceOverride: (
    componentId: string,
    quantity: number,
    manualUnitPrice: string | null,
  ) => Promise<unknown>;
  refreshPricing: (quoteId: string) => Promise<{ refreshed_items: number }>;
  // M1.11 — add-ons / lead times / expedite / VAT totals
  listAddOnDefs: () => Promise<AddOnDefOut[]>;
  addAddOn: (componentId: string, body: AddOnCreateBody) => Promise<unknown>;
  updateAddOn: (
    addOnId: string,
    body: { manual_is_required?: boolean | null; name?: string },
  ) => Promise<unknown>;
  removeAddOn: (addOnId: string) => Promise<void>;
  setAddOnPrice: (
    addOnId: string,
    quantity: number,
    manualPrice: string | null,
  ) => Promise<unknown>;
  setLeadTime: (
    componentId: string,
    quantity: number,
    manualLeadTimeDays: number | null,
  ) => Promise<unknown>;
  setExpediteOptions: (componentId: string, options: ExpediteTierBody[]) => Promise<unknown>;
  applyLeadTimesToAll: (
    quoteId: string,
    body: { standard_lead_time_days?: number | null; tiers: ExpediteTierBody[] },
  ) => Promise<unknown>;
  getQuoteTotals: (quoteId: string) => Promise<QuoteTotals>;
  // M3.4 — Bulk Create Line Items (prefill + explicit Accept)
  getBulkCreatePrefill: (quoteId: string) => Promise<BulkCreatePrefill>;
  bulkCreateLineItems: (quoteId: string, rows: BulkCreateRowBody[]) => Promise<QuoteSummary>;
}

/** Build an estimating API client bound to the current Clerk session token. */
export function useEstimatingApi(): EstimatingApi {
  const { getToken } = useAuth();
  return useMemo<EstimatingApi>(() => {
    const token: TokenGetter = () => getToken();
    return {
      getQuote: (quoteId) => apiFetch(`/api/quotes/${quoteId}`, token),
      getCosting: (componentId) => apiFetch(`/api/components/${componentId}/costing`, token),
      materialTree: () => apiFetch('/api/materials/tree', token),
      searchMaterials: (q) =>
        apiFetch(`/api/materials?q=${encodeURIComponent(q)}`, token),
      updateMaterial: (materialId, body) =>
        apiFetch(`/api/materials/${materialId}`, token, { method: 'PATCH', body }),
      listProcesses: () => apiFetch('/api/processes', token),
      listOperationDefs: (q) =>
        apiFetch(`/api/operation-defs?q=${encodeURIComponent(q)}`, token),
      setComponentMaterial: (componentId, materialId) =>
        apiFetch(`/api/components/${componentId}/material`, token, {
          method: 'PATCH',
          body: { material_id: materialId },
        }),
      setComponentProcess: (componentId, processId, keepOperations) =>
        apiFetch(`/api/components/${componentId}/process`, token, {
          method: 'PATCH',
          body: { process_id: processId, keep_operations: keepOperations },
        }),
      addOperation: (componentId, body) =>
        apiFetch(`/api/components/${componentId}/operations`, token, {
          method: 'POST',
          body,
        }),
      updateOperation: (operationId, body) =>
        apiFetch(`/api/operations/${operationId}`, token, { method: 'PATCH', body }),
      duplicateOperation: (operationId) =>
        apiFetch(`/api/operations/${operationId}/duplicate`, token, { method: 'POST' }),
      removeOperation: (operationId) =>
        apiFetch(`/api/operations/${operationId}`, token, { method: 'DELETE' }),
      reorderOperations: (componentId, operationIds) =>
        apiFetch(`/api/components/${componentId}/operations/order`, token, {
          method: 'PUT',
          body: { operation_ids: operationIds },
        }),
      setCellOverride: (operationId, quantity, manualCost) =>
        apiFetch(`/api/operations/${operationId}/cells/${quantity}`, token, {
          method: 'PATCH',
          body: { manual_cost: manualCost },
        }),
      kalkCheck: (formula) =>
        apiFetch('/api/kalk/check', token, { method: 'POST', body: { formula } }),
      getKalkReport: (operationId) => apiFetch(`/api/operations/${operationId}/kalk`, token),
      setVariableOverrides: (operationId, overrides) =>
        apiFetch(`/api/operations/${operationId}/variables`, token, {
          method: 'PUT',
          body: { overrides },
        }),
      getPricing: (componentId) => apiFetch(`/api/components/${componentId}/pricing`, token),
      addPricingItem: (componentId, body) =>
        apiFetch(`/api/components/${componentId}/pricing-items`, token, {
          method: 'POST',
          body,
        }),
      updatePricingItem: (pricingItemId, body) =>
        apiFetch(`/api/pricing-items/${pricingItemId}`, token, { method: 'PATCH', body }),
      reorderPricingItems: (componentId, pricingItemIds) =>
        apiFetch(`/api/components/${componentId}/pricing-items/order`, token, {
          method: 'PUT',
          body: { pricing_item_ids: pricingItemIds },
        }),
      listPricingItemDefs: () => apiFetch('/api/pricing-item-defs', token),
      listDiscountDefs: () => apiFetch('/api/discount-defs', token),
      removePricingItem: (pricingItemId) =>
        apiFetch(`/api/pricing-items/${pricingItemId}`, token, { method: 'DELETE' }),
      setPricingItemPct: (pricingItemId, quantity, manualPct) =>
        apiFetch(`/api/pricing-items/${pricingItemId}/cells/${quantity}`, token, {
          method: 'PATCH',
          body: { manual_pct: manualPct },
        }),
      addDiscount: (componentId, body) =>
        apiFetch(`/api/components/${componentId}/discounts`, token, { method: 'POST', body }),
      removeDiscount: (discountId) =>
        apiFetch(`/api/discounts/${discountId}`, token, { method: 'DELETE' }),
      setDiscountPct: (discountId, quantity, manualPct) =>
        apiFetch(`/api/discounts/${discountId}/cells/${quantity}`, token, {
          method: 'PATCH',
          body: { manual_pct: manualPct },
        }),
      setUnitPriceOverride: (componentId, quantity, manualUnitPrice) =>
        apiFetch(`/api/components/${componentId}/price/${quantity}`, token, {
          method: 'PATCH',
          body: { manual_unit_price: manualUnitPrice },
        }),
      refreshPricing: (quoteId) =>
        apiFetch(`/api/quotes/${quoteId}/refresh-pricing`, token, { method: 'POST' }),
      getBulkCreatePrefill: (quoteId) => apiFetch(`/api/quotes/${quoteId}/bulk-create`, token),
      bulkCreateLineItems: (quoteId, rows) =>
        apiFetch(`/api/quotes/${quoteId}/bulk-create`, token, { method: 'POST', body: { rows } }),
      listAddOnDefs: () => apiFetch('/api/add-on-defs', token),
      addAddOn: (componentId, body) =>
        apiFetch(`/api/components/${componentId}/add-ons`, token, { method: 'POST', body }),
      updateAddOn: (addOnId, body) =>
        apiFetch(`/api/add-ons/${addOnId}`, token, { method: 'PATCH', body }),
      removeAddOn: (addOnId) => apiFetch(`/api/add-ons/${addOnId}`, token, { method: 'DELETE' }),
      setAddOnPrice: (addOnId, quantity, manualPrice) =>
        apiFetch(`/api/add-ons/${addOnId}/cells/${quantity}`, token, {
          method: 'PATCH',
          body: { manual_price: manualPrice },
        }),
      setLeadTime: (componentId, quantity, manualLeadTimeDays) =>
        apiFetch(`/api/components/${componentId}/lead-time/${quantity}`, token, {
          method: 'PATCH',
          body: { manual_lead_time_days: manualLeadTimeDays },
        }),
      setExpediteOptions: (componentId, options) =>
        apiFetch(`/api/components/${componentId}/expedite-options`, token, {
          method: 'PUT',
          body: { options },
        }),
      applyLeadTimesToAll: (quoteId, body) =>
        apiFetch(`/api/quotes/${quoteId}/lead-times/apply-to-all`, token, {
          method: 'POST',
          body,
        }),
      getQuoteTotals: (quoteId) => apiFetch(`/api/quotes/${quoteId}/totals`, token),
    };
  }, [getToken]);
}
