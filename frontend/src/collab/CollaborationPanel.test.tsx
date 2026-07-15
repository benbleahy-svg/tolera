import { beforeEach, describe, expect, it, vi } from 'vitest';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

import { renderWithProviders } from '../test/render';
import { type BoundSelection, CollaborationPanel } from './CollaborationPanel';

const listChannels = vi.fn();
const createChannel = vi.fn();
const listMessages = vi.fn();
const postMessage = vi.fn();
const editMessage = vi.fn();
const deleteMessage = vi.fn();
const assignTask = vi.fn();
const listMembers = vi.fn();

vi.mock('./api', async () => {
  const actual = await vi.importActual<typeof import('./api')>('./api');
  return {
    ...actual,
    useCollabApi: () => ({
      listChannels,
      createChannel,
      listMessages,
      postMessage,
      editMessage,
      deleteMessage,
      assignTask,
      listTasks: vi.fn(),
      updateTask: vi.fn(),
      listNotifications: vi.fn(),
      markNotification: vi.fn(),
      listMembers,
    }),
  };
});

const TEAM = {
  id: 'ch-team',
  part_id: 'p1',
  quote_id: null,
  scope: 'team' as const,
  label: null,
  created_at: '2026-07-14T00:00:00Z',
};

const MEMBERS = [
  { id: 'u1', email: 'estimator@fechner.example', first_name: 'Eva', last_name: 'Schmidt' },
  { id: 'u2', email: 'engineer@fechner.example', first_name: 'Max', last_name: 'Bauer' },
];

function message(overrides: Record<string, unknown> = {}) {
  return {
    id: 'm1',
    channel_id: 'ch-team',
    author_id: 'u1',
    parent_id: null,
    body: 'Diese Passung prüfen',
    mentions: [],
    annotation: null,
    edited_at: null,
    deleted: false,
    created_at: '2026-07-14T01:00:00Z',
    ...overrides,
  };
}

const FACE_SELECTION: BoundSelection = {
  kind: 'face',
  geometry_ref: { file_id: 'f1', entity: { bodyId: 'b0', kind: 'face', index: 7 } },
  label: 'Fläche 7',
};

describe('CollaborationPanel', () => {
  beforeEach(() => {
    for (const fn of [
      listChannels,
      createChannel,
      listMessages,
      postMessage,
      editMessage,
      deleteMessage,
      assignTask,
      listMembers,
    ]) {
      fn.mockReset();
    }
    listChannels.mockResolvedValue([TEAM]);
    listMembers.mockResolvedValue(MEMBERS);
    listMessages.mockResolvedValue([]);
    postMessage.mockResolvedValue(message());
    assignTask.mockResolvedValue({ id: 't1' });
  });

  it('auto-shows the TEAM channel and its messages', async () => {
    listMessages.mockResolvedValue([message()]);
    await renderWithProviders(<CollaborationPanel partId="p1" />);
    expect(await screen.findByRole('tab', { name: 'TEAM' })).toBeInTheDocument();
    expect(await screen.findByText('Diese Passung prüfen')).toBeInTheDocument();
  });

  it('posts a message pinned to the picked 3D face', async () => {
    const user = userEvent.setup();
    await renderWithProviders(
      <CollaborationPanel partId="p1" selection={FACE_SELECTION} />,
    );
    await screen.findByRole('tab', { name: 'TEAM' });

    await user.type(screen.getByLabelText('Nachricht'), '@Max diese Löcher maskieren');
    await user.click(screen.getByRole('button', { name: 'Senden' }));

    await waitFor(() => expect(postMessage).toHaveBeenCalledTimes(1));
    const [channelId, input] = postMessage.mock.calls[0];
    expect(channelId).toBe('ch-team');
    expect(input.body).toBe('@Max diese Löcher maskieren');
    // The face locator (M2.7 EntityRef) rides along so a click re-focuses it.
    expect(input.annotation).toEqual({
      kind: 'face',
      geometry_ref: { file_id: 'f1', entity: { bodyId: 'b0', kind: 'face', index: 7 } },
    });
  });

  it('clicking a message annotation re-focuses the exact feature', async () => {
    const annotation = {
      id: 'a1',
      kind: 'face' as const,
      geometry_ref: { file_id: 'f1', entity: { bodyId: 'b0', kind: 'face', index: 7 } },
      note: null,
    };
    listMessages.mockResolvedValue([message({ annotation })]);
    const onFocus = vi.fn();
    await renderWithProviders(
      <CollaborationPanel partId="p1" onFocusAnnotation={onFocus} />,
    );
    await userEvent.click(await screen.findByRole('button', { name: 'Fläche anzeigen' }));
    expect(onFocus).toHaveBeenCalledWith(annotation);
  });

  it('assigns a task on a face-bound message (→ Dashboard)', async () => {
    const annotation = {
      id: 'a1',
      kind: 'face' as const,
      geometry_ref: { file_id: 'f1', entity: { bodyId: 'b0', kind: 'face', index: 7 } },
      note: null,
    };
    listMessages.mockResolvedValue([message({ annotation })]);
    const user = userEvent.setup();
    await renderWithProviders(<CollaborationPanel partId="p1" />);

    await user.click(await screen.findByRole('button', { name: 'Aufgabe zuweisen' }));
    const form = screen.getByRole('button', { name: 'Aufgabe erstellen' }).closest('form')!;
    await user.selectOptions(within(form).getByRole('combobox'), 'u2');
    await user.click(within(form).getByRole('button', { name: 'Aufgabe erstellen' }));

    await waitFor(() => expect(assignTask).toHaveBeenCalledTimes(1));
    const [partId, input] = assignTask.mock.calls[0];
    expect(partId).toBe('p1');
    expect(input.assignee_id).toBe('u2');
    expect(input.annotation_id).toBe('a1'); // task bound to the picked face
  });

  it('offers Edit/Delete only on the caller’s own messages', async () => {
    listMessages.mockResolvedValue([
      message({ id: 'mine', author_id: 'u1', body: 'meine' }),
      message({ id: 'theirs', author_id: 'u2', body: 'fremde' }),
    ]);
    await renderWithProviders(<CollaborationPanel partId="p1" />);

    const mine = (await screen.findByText('meine')).closest('li')!;
    const theirs = screen.getByText('fremde').closest('li')!;
    expect(within(mine).queryByRole('button', { name: 'Löschen' })).toBeInTheDocument();
    expect(within(theirs).queryByRole('button', { name: 'Löschen' })).not.toBeInTheDocument();
  });
});
