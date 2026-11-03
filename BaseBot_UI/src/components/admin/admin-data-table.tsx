"use client";

import * as React from "react";
import { useAdminList } from "@/lib/admin";

export type AdminColumn<T> = {
  key: string;
  header: string;
  render: (item: T) => React.ReactNode;
  sortKey?: string;
};

/** Compact admin table: search, sort, pagination, loading/empty/error. */
export function AdminDataTable<T extends { id: string }>({
  title,
  path,
  columns,
  extraParams = {},
  sortKeys = [],
  actions,
}: {
  title: string;
  path: string;
  columns: AdminColumn<T>[];
  extraParams?: Record<string, string | undefined>;
  sortKeys?: string[];
  actions?: (item: T, refresh: () => void) => React.ReactNode;
}) {
  const list = useAdminList<T>(path, extraParams);
  const pages = Math.max(1, Math.ceil(list.total / list.pageSize));

  return (
    <section>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg text-primary">{title}</h2>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="search"
            value={list.search}
            onChange={(event) => {
              list.setSearch(event.target.value);
              list.setPage(1);
            }}
            placeholder="Search…"
            aria-label={`Search ${title}`}
            className="h-8 w-48 rounded-sm border border-strong bg-inset px-2.5 text-sm text-primary placeholder:text-tertiary"
          />
          {sortKeys.length > 0 && (
            <select
              aria-label="Sort by"
              value={list.sort}
              onChange={(event) => {
                list.setSort(event.target.value);
                list.setPage(1);
              }}
              className="h-8 rounded-sm border border-strong bg-inset px-2 text-sm text-primary"
            >
              <option value="">Newest</option>
              {sortKeys.map((key) => (
                <option key={key} value={key}>
                  {key}
                </option>
              ))}
            </select>
          )}
          <button
            type="button"
            onClick={list.refresh}
            className="rounded-sm border border-subtle px-2.5 py-1.5 text-xs text-secondary hover:text-primary"
          >
            Refresh
          </button>
        </div>
      </div>

      {list.updatedAt && (
        <p className="mb-2 text-xs text-tertiary">
          Last updated{" "}
          {list.updatedAt.toLocaleTimeString("en-GB", {
            timeZone: "Africa/Dar_es_Salaam",
          })}{" "}
          · {list.total} rows
        </p>
      )}

      {list.error && (
        <p className="rounded-sm border border-danger-500/40 bg-surface p-3 text-sm text-danger-400">
          {list.error}
        </p>
      )}
      {list.loading && !list.error && (
        <p className="rounded-sm border border-subtle bg-surface p-6 text-sm text-secondary">
          Loading…
        </p>
      )}
      {!list.loading && !list.error && list.items.length === 0 && (
        <p className="rounded-sm border border-subtle bg-surface p-6 text-sm text-secondary">
          Nothing here yet.
        </p>
      )}

      {!list.loading && !list.error && list.items.length > 0 && (
        <div className="overflow-x-auto rounded-sm border border-subtle">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-subtle bg-inset text-xs text-tertiary">
                {columns.map((column) => (
                  <th key={column.key} className="px-3 py-2 font-medium">
                    {column.header}
                  </th>
                ))}
                {actions && <th className="px-3 py-2 font-medium">Actions</th>}
              </tr>
            </thead>
            <tbody>
              {list.items.map((item) => (
                <tr key={item.id} className="border-b border-subtle last:border-0">
                  {columns.map((column) => (
                    <td key={column.key} className="px-3 py-2 align-top text-secondary">
                      {column.render(item)}
                    </td>
                  ))}
                  {actions && (
                    <td className="px-3 py-2 align-top">{actions(item, list.refresh)}</td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {pages > 1 && (
        <div className="mt-3 flex items-center gap-2 text-sm text-secondary">
          <button
            type="button"
            disabled={list.page <= 1}
            onClick={() => list.setPage(list.page - 1)}
            className="rounded-sm border border-subtle px-2 py-1 disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-xs text-tertiary">
            Page {list.page} of {pages}
          </span>
          <button
            type="button"
            disabled={list.page >= pages}
            onClick={() => list.setPage(list.page + 1)}
            className="rounded-sm border border-subtle px-2 py-1 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </section>
  );
}
