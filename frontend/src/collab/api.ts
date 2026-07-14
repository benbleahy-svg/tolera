/**
 * Collaboration API types + the `useCollabApi` hook (M2.11).
 *
 * Mirrors the FastAPI `/api` collaboration contract: TEAM/EXTERNAL channels,
 * feature/region-bound messages, `@mention`, Assign Task → Dashboard, and the
 * caller's notification inbox. All JSON via `apiFetch`. Tests mock this module
 * wholesale (no Clerk/network).
 */

import { useMemo } from 'react';
import { useAuth } from '@clerk/clerk-react';

import { apiFetch, type TokenGetter } from '../api/client';

export type ChannelScope = 'team' | 'external';
export type TaskStatus = 'open' | 'overdue' | 'resolved';
export type AnnotationKind = 'face' | 'region';

/** A face/region locator a message binds to. 3D face → `{file_id, entity}` (the
 *  M2.7 EntityRef); PDF region → `{file_id, page, rect}` (M2.2 pdf-units). */
export interface GeometryRef {
  file_id: string;
  entity?: { bodyId: string; kind: string; index: number };
  page?: number;
  rect?: { x: number; y: number; width: number; height: number };
}

export interface Annotation {
  id: string;
  kind: AnnotationKind;
  geometry_ref: GeometryRef;
  note: string | null;
}

export interface Channel {
  id: string;
  part_id: string;
  quote_id: string | null;
  scope: ChannelScope;
  label: string | null;
  created_at: string;
}

export interface Message {
  id: string;
  channel_id: string;
  author_id: string | null;
  parent_id: string | null;
  body: string;
  mentions: string[];
  annotation: Annotation | null;
  edited_at: string | null;
  deleted: boolean;
  created_at: string;
}

export interface Task {
  id: string;
  part_id: string | null;
  quote_id: string | null;
  annotation_id: string | null;
  assignee_id: string | null;
  created_by: string | null;
  message: string | null;
  due_date: string | null;
  status: TaskStatus;
  resolved_at: string | null;
  created_at: string;
}

export interface Notification {
  id: string;
  kind: string;
  payload: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export interface Member {
  id: string;
  email: string;
  first_name: string | null;
  last_name: string | null;
}

/** Display label for a teammate — full name if known, else the email. */
export function memberLabel(m: Member): string {
  const name = [m.first_name, m.last_name].filter(Boolean).join(' ').trim();
  return name || m.email;
}

export interface AnnotationDraft {
  kind: AnnotationKind;
  geometry_ref: GeometryRef;
  note?: string | null;
}

export interface PostMessageInput {
  body: string;
  annotation?: AnnotationDraft;
  parent_id?: string;
  mentions?: string[];
}

export interface AssignTaskInput {
  assignee_id: string;
  message?: string;
  due_date?: string;
  annotation_id?: string;
  quote_id?: string;
}

export interface CollabApi {
  listChannels: (partId: string) => Promise<Channel[]>;
  createChannel: (
    partId: string,
    input: { scope: ChannelScope; label?: string; quote_id?: string },
  ) => Promise<Channel>;
  listMessages: (channelId: string) => Promise<Message[]>;
  postMessage: (channelId: string, input: PostMessageInput) => Promise<Message>;
  editMessage: (messageId: string, body: string) => Promise<Message>;
  deleteMessage: (messageId: string) => Promise<void>;
  assignTask: (partId: string, input: AssignTaskInput) => Promise<Task>;
  listTasks: (params?: { assignee_id?: string; status?: TaskStatus }) => Promise<Task[]>;
  updateTask: (taskId: string, status: 'open' | 'resolved') => Promise<Task>;
  listNotifications: () => Promise<Notification[]>;
  markNotification: (notificationId: string, read: boolean) => Promise<Notification>;
  listMembers: () => Promise<Member[]>;
}

function query(params?: Record<string, string | undefined>): string {
  if (!params) return '';
  const pairs = Object.entries(params).filter(([, v]) => v != null) as [string, string][];
  return pairs.length ? `?${new URLSearchParams(pairs).toString()}` : '';
}

export function useCollabApi(): CollabApi {
  const { getToken } = useAuth();
  return useMemo<CollabApi>(() => {
    const token: TokenGetter = () => getToken();
    return {
      listChannels: (partId) => apiFetch(`/api/parts/${partId}/channels`, token),
      createChannel: (partId, input) =>
        apiFetch(`/api/parts/${partId}/channels`, token, { method: 'POST', body: input }),
      listMessages: (channelId) => apiFetch(`/api/channels/${channelId}/messages`, token),
      postMessage: (channelId, input) =>
        apiFetch(`/api/channels/${channelId}/messages`, token, { method: 'POST', body: input }),
      editMessage: (messageId, body) =>
        apiFetch(`/api/messages/${messageId}`, token, { method: 'PATCH', body: { body } }),
      deleteMessage: (messageId) =>
        apiFetch(`/api/messages/${messageId}`, token, { method: 'DELETE' }),
      assignTask: (partId, input) =>
        apiFetch(`/api/parts/${partId}/tasks`, token, { method: 'POST', body: input }),
      listTasks: (params) => apiFetch(`/api/tasks${query(params)}`, token),
      updateTask: (taskId, status) =>
        apiFetch(`/api/tasks/${taskId}`, token, { method: 'PATCH', body: { status } }),
      listNotifications: () => apiFetch('/api/notifications', token),
      markNotification: (notificationId, read) =>
        apiFetch(`/api/notifications/${notificationId}`, token, {
          method: 'PATCH',
          body: { read },
        }),
      listMembers: () => apiFetch('/api/org/members', token),
    };
  }, [getToken]);
}
