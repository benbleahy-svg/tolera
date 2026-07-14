/**
 * The viewer's collaboration panel (M2.11, spec #collab).
 *
 * TEAM (internal) + EXTERNAL (per vendor/customer) channels on a part. Post a
 * message optionally **bound to the current viewer selection** (a picked 3D
 * face or a PDF region), `@mention` teammates, reply / edit / delete your own
 * messages, and **Assign Task** (surfaces on the Dashboard). Clicking a
 * message's annotation calls `onFocusAnnotation` so the viewer re-focuses the
 * exact feature. Prop-driven and viewer-agnostic; both the CAD and PDF viewers
 * mount it and feed it their current selection.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { useSession } from '../session/session';
import {
  type Annotation,
  type AnnotationDraft,
  type Channel,
  type Member,
  memberLabel,
  type Message,
  useCollabApi,
} from './api';

/** The current viewer selection a new message can be pinned to. */
export interface BoundSelection {
  kind: AnnotationDraft['kind'];
  geometry_ref: AnnotationDraft['geometry_ref'];
  /** Short human label for the affordance, e.g. "Fläche 7" / "Bereich S. 1". */
  label: string;
}

export interface CollaborationPanelProps {
  partId: string;
  selection?: BoundSelection | null;
  onFocusAnnotation?: (annotation: Annotation) => void;
}

export function CollaborationPanel({
  partId,
  selection,
  onFocusAnnotation,
}: CollaborationPanelProps): React.ReactElement {
  const { t } = useTranslation();
  const api = useCollabApi();
  const me = useSession();
  const canPost = me.effective_permissions.includes('quote_annotate');

  const [channels, setChannels] = useState<Channel[]>([]);
  const [activeChannelId, setActiveChannelId] = useState<string | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [messages, setMessages] = useState<Message[]>([]);
  const [error, setError] = useState<string | null>(null);

  const memberName = useCallback(
    (id: string | null): string => {
      if (!id) return t('collab.system');
      const m = members.find((x) => x.id === id);
      return m ? memberLabel(m) : t('collab.unknown_member');
    },
    [members, t],
  );

  const reload = useCallback(async () => {
    try {
      const [chs, mem] = await Promise.all([api.listChannels(partId), api.listMembers()]);
      setChannels(chs);
      setMembers(mem);
      setActiveChannelId((prev) => prev ?? chs.find((c) => c.scope === 'team')?.id ?? null);
    } catch {
      setError(t('collab.load_error'));
    }
  }, [api, partId, t]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const loadMessages = useCallback(
    async (channelId: string) => {
      try {
        setMessages(await api.listMessages(channelId));
      } catch {
        setError(t('collab.load_error'));
      }
    },
    [api, t],
  );

  useEffect(() => {
    if (activeChannelId) void loadMessages(activeChannelId);
  }, [activeChannelId, loadMessages]);

  const teamChannel = useMemo(() => channels.find((c) => c.scope === 'team'), [channels]);
  const externalChannels = useMemo(
    () => channels.filter((c) => c.scope === 'external'),
    [channels],
  );

  const addExternalChannel = async () => {
    const label = window.prompt(t('collab.new_channel_prompt')) ?? '';
    if (!label.trim()) return;
    const created = await api.createChannel(partId, { scope: 'external', label: label.trim() });
    setChannels((prev) => [...prev, created]);
    setActiveChannelId(created.id);
  };

  return (
    <section className="collab-panel" aria-label={t('collab.title')}>
      <div role="tablist" className="collab-tabs" aria-label={t('collab.channels')}>
        {teamChannel && (
          <ChannelTab
            label={t('collab.team')}
            active={activeChannelId === teamChannel.id}
            onClick={() => setActiveChannelId(teamChannel.id)}
          />
        )}
        {externalChannels.map((c) => (
          <ChannelTab
            key={c.id}
            label={c.label ?? t('collab.external')}
            active={activeChannelId === c.id}
            onClick={() => setActiveChannelId(c.id)}
          />
        ))}
        {canPost && (
          <button type="button" className="collab-add-channel" onClick={() => void addExternalChannel()}>
            {t('collab.add_external')}
          </button>
        )}
      </div>

      {error && <p role="alert" className="collab-error">{error}</p>}

      <ul className="collab-messages">
        {messages.map((m) => (
          <MessageRow
            key={m.id}
            message={m}
            authorName={memberName(m.author_id)}
            isOwn={m.author_id === me.user.id}
            canPost={canPost}
            members={members}
            onFocusAnnotation={onFocusAnnotation}
            onEdit={async (body) => {
              await api.editMessage(m.id, body);
              if (activeChannelId) await loadMessages(activeChannelId);
            }}
            onDelete={async () => {
              await api.deleteMessage(m.id);
              if (activeChannelId) await loadMessages(activeChannelId);
            }}
            onAssignTask={async (assigneeId, note) => {
              await api.assignTask(partId, {
                assignee_id: assigneeId,
                message: note || undefined,
                annotation_id: m.annotation?.id,
              });
            }}
          />
        ))}
        {messages.length === 0 && <li className="collab-empty">{t('collab.no_messages')}</li>}
      </ul>

      {canPost && activeChannelId && (
        <Composer
          members={members}
          selection={selection ?? null}
          onPost={async (body, mentions, attach) => {
            const annotation: AnnotationDraft | undefined =
              attach && selection
                ? { kind: selection.kind, geometry_ref: selection.geometry_ref }
                : undefined;
            await api.postMessage(activeChannelId, { body, mentions, annotation });
            await loadMessages(activeChannelId);
          }}
        />
      )}
    </section>
  );
}

function ChannelTab({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}): React.ReactElement {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      className={active ? 'collab-tab is-active' : 'collab-tab'}
      onClick={onClick}
    >
      {label}
    </button>
  );
}

function MessageRow({
  message,
  authorName,
  isOwn,
  canPost,
  members,
  onFocusAnnotation,
  onEdit,
  onDelete,
  onAssignTask,
}: {
  message: Message;
  authorName: string;
  isOwn: boolean;
  canPost: boolean;
  members: Member[];
  onFocusAnnotation?: (a: Annotation) => void;
  onEdit: (body: string) => Promise<void>;
  onDelete: () => Promise<void>;
  onAssignTask: (assigneeId: string, note: string) => Promise<void>;
}): React.ReactElement {
  const { t } = useTranslation();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(message.body);
  const [assigning, setAssigning] = useState(false);

  if (message.deleted) {
    return <li className="collab-message is-deleted">{t('collab.deleted')}</li>;
  }

  return (
    <li className="collab-message">
      <header className="collab-message-head">
        <span className="collab-author">{authorName}</span>
        {message.edited_at && <span className="collab-edited">{t('collab.edited')}</span>}
      </header>

      {editing ? (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void onEdit(draft).then(() => setEditing(false));
          }}
        >
          <textarea value={draft} onChange={(e) => setDraft(e.target.value)} aria-label={t('collab.edit')} />
          <button type="submit">{t('collab.save')}</button>
        </form>
      ) : (
        <p className="collab-body">{message.body}</p>
      )}

      {message.annotation && (
        <button
          type="button"
          className="collab-annotation-chip"
          onClick={() => onFocusAnnotation?.(message.annotation as Annotation)}
        >
          {message.annotation.kind === 'face' ? t('collab.chip_face') : t('collab.chip_region')}
        </button>
      )}

      {canPost && (
        <div className="collab-message-actions">
          {isOwn && !editing && (
            <>
              <button type="button" onClick={() => setEditing(true)}>{t('collab.edit')}</button>
              <button type="button" onClick={() => void onDelete()}>{t('collab.delete')}</button>
            </>
          )}
          <button type="button" onClick={() => setAssigning((v) => !v)}>
            {t('collab.assign_task')}
          </button>
        </div>
      )}

      {assigning && (
        <AssignTaskForm
          members={members}
          onSubmit={async (assigneeId, note) => {
            await onAssignTask(assigneeId, note);
            setAssigning(false);
          }}
        />
      )}
    </li>
  );
}

function AssignTaskForm({
  members,
  onSubmit,
}: {
  members: Member[];
  onSubmit: (assigneeId: string, note: string) => Promise<void>;
}): React.ReactElement {
  const { t } = useTranslation();
  const [assignee, setAssignee] = useState(members[0]?.id ?? '');
  const [note, setNote] = useState('');

  return (
    <form
      className="collab-assign"
      onSubmit={(e) => {
        e.preventDefault();
        if (assignee) void onSubmit(assignee, note);
      }}
    >
      <label>
        {t('collab.assignee')}
        <select value={assignee} onChange={(e) => setAssignee(e.target.value)}>
          {members.map((m) => (
            <option key={m.id} value={m.id}>{memberLabel(m)}</option>
          ))}
        </select>
      </label>
      <input
        type="text"
        value={note}
        placeholder={t('collab.task_note')}
        onChange={(e) => setNote(e.target.value)}
        aria-label={t('collab.task_note')}
      />
      <button type="submit">{t('collab.create_task')}</button>
    </form>
  );
}

function Composer({
  members,
  selection,
  onPost,
}: {
  members: Member[];
  selection: BoundSelection | null;
  onPost: (body: string, mentions: string[], attach: boolean) => Promise<void>;
}): React.ReactElement {
  const { t } = useTranslation();
  const [body, setBody] = useState('');
  const [mentions, setMentions] = useState<string[]>([]);
  const [attach, setAttach] = useState(true);

  return (
    <form
      className="collab-composer"
      onSubmit={(e) => {
        e.preventDefault();
        if (!body.trim()) return;
        void onPost(body.trim(), mentions, attach && !!selection).then(() => {
          setBody('');
          setMentions([]);
        });
      }}
    >
      <textarea
        value={body}
        onChange={(e) => setBody(e.target.value)}
        placeholder={t('collab.composer_placeholder')}
        aria-label={t('collab.message')}
      />
      {selection && (
        <label className="collab-attach">
          <input type="checkbox" checked={attach} onChange={(e) => setAttach(e.target.checked)} />
          {t('collab.attach_selection', { label: selection.label })}
        </label>
      )}
      <label className="collab-mentions">
        {t('collab.mention')}
        <select
          multiple
          value={mentions}
          onChange={(e) =>
            setMentions(Array.from(e.target.selectedOptions, (o) => o.value))
          }
        >
          {members.map((m) => (
            <option key={m.id} value={m.id}>{memberLabel(m)}</option>
          ))}
        </select>
      </label>
      <button type="submit" disabled={!body.trim()}>{t('collab.post')}</button>
    </form>
  );
}
