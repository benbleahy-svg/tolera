/**
 * Estimating API (M1.7) — component costing, material picker, processes and the
 * operation library, bound to the Clerk session token once (the `useQuotesApi`
 * pattern; tests mock this module wholesale).
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiFetch, type TokenGetter } from '../api/client';
import type {
  ClassNode,
  ComponentCosting,
  MaterialOut,
  MaterialSearchHit,
  MaterialUpdateBody,
  OperationCreateBody,
  OperationDefOut,
  OperationUpdateBody,
  ProcessOut,
  QuoteSummary,
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
    };
  }, [getToken]);
}
