import type { ReactNode } from 'react'
import { cx } from './cx'

export type Column<T> = { key: string; header: string; render: (row: T) => ReactNode; className?: string }

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
}: {
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  onRowClick?: (row: T) => void
}) {
  return (
    <div className="shadow-inset rounded-panel overflow-x-auto p-4">
      <table className="w-full text-left text-[13px]">
        <thead>
          <tr>
            {columns.map((c) => (
              <th key={c.key} className={cx('text-secondary pb-3 text-[11px] leading-4 font-normal', c.className)}>
                {c.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={rowKey(r)}
              onClick={onRowClick && (() => onRowClick(r))}
              onKeyDown={onRowClick && ((e) => e.key === 'Enter' && onRowClick(r))}
              tabIndex={onRowClick ? 0 : undefined}
              className={cx('border-secondary/15 border-t', onRowClick && 'hover:bg-accent-fill cursor-pointer')}
            >
              {columns.map((c) => (
                <td key={c.key} className={cx('py-3', c.className)}>
                  {c.render(r)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
