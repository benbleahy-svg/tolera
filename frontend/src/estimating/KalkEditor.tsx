/**
 * The Kalk formula editor chrome (spec #kalk "Editor chrome", DemoG/07): a
 * line-numbered monospace editor with a "Kalk-Formel — <name>" header and the
 * CHECK affordance (static validation, line-numbered errors). Used by the
 * operation drawer, the pricing-item editor and the Configure-side definition
 * editors. Version history / last-saved-by need backend support and are logged
 * as OPEN in DECISIONS.md — deliberately absent here.
 */

import { useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import type { KalkCheckResult } from './types';

interface Props {
  value: string;
  onChange: (next: string) => void;
  /** Formula owner shown in the header ("Kalk-Formel — Fräsen"). */
  name?: string;
  onCheck?: (formula: string) => Promise<KalkCheckResult>;
  rows?: number;
  disabled?: boolean;
}

export function KalkEditor({ value, onChange, name, onCheck, rows = 8, disabled }: Props) {
  const { t } = useTranslation();
  const [checkResult, setCheckResult] = useState<KalkCheckResult | null>(null);
  const gutterRef = useRef<HTMLPreElement | null>(null);
  // invalidates in-flight CHECK responses once the formula has changed —
  // a slow response must never label a newer draft as checked
  const checkSeq = useRef(0);

  const lineCount = Math.max(value.split('\n').length, 1);
  const lines = Array.from({ length: lineCount }, (_, i) => i + 1).join('\n');

  return (
    <div className="est-kalk-editor-block">
      <h4>
        {name ? t('kalk.formula_titled', { name }) : t('kalk.formula')}
      </h4>
      <div className="est-kalk-editor-frame">
        <pre className="est-kalk-gutter" aria-hidden="true" ref={gutterRef}>
          {lines}
        </pre>
        <textarea
          className="est-kalk-editor"
          aria-label={name ? t('kalk.formula_titled', { name }) : t('kalk.formula')}
          spellCheck={false}
          rows={rows}
          value={value}
          disabled={disabled}
          onChange={(e) => {
            checkSeq.current += 1;
            onChange(e.target.value);
            setCheckResult(null);
          }}
          onScroll={(e) => {
            if (gutterRef.current) gutterRef.current.scrollTop = e.currentTarget.scrollTop;
          }}
          placeholder={t('kalk.formula_placeholder')}
        />
      </div>
      {checkResult && (
        <p className={checkResult.ok ? 'est-kalk-ok' : 'est-kalk-errors'} role="status">
          {checkResult.ok
            ? t('kalk.check_ok')
            : checkResult.errors
                .map((err) =>
                  err.line !== null
                    ? t('kalk.error_at_line', { line: err.line, message: err.message })
                    : err.message,
                )
                .join('\n')}
        </p>
      )}
      {onCheck && (
        <div className="est-actions est-kalk-check-row">
          <button
            type="button"
            onClick={() => {
              const mySeq = ++checkSeq.current;
              void onCheck(value)
                .then((result) => {
                  if (mySeq === checkSeq.current) setCheckResult(result);
                })
                .catch(() => {
                  if (mySeq !== checkSeq.current) return;
                  setCheckResult({
                    ok: false,
                    errors: [
                      {
                        code: 'check_failed',
                        message: t('kalk.check_failed'),
                        line: null,
                        col: null,
                      },
                    ],
                  });
                });
            }}
            disabled={value.trim() === ''}
          >
            {t('kalk.check')}
          </button>
        </div>
      )}
    </div>
  );
}
