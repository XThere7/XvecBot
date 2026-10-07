"use client";

import * as React from "react";
import {
  flexRender,
  getCoreRowModel,
  useReactTable,
  type ColumnDef,
  type SortingState,
} from "@tanstack/react-table";
import { cn } from "@/lib/cn";
import { Skeleton } from "./skeleton";

export type DataTableColumn<T> = {
  id: string;
  header: string;
  cell: (row: T) => React.ReactNode;
  /** Dropped on tablet, and shown as a stacked-card caption on mobile. */
  secondary?: boolean;
  /** The column whose value becomes the mobile card heading. */
  primary?: boolean;
  headerClassName?: string;
  cellClassName?: string;
  align?: "left" | "right";
};

export type DataTableProps<T> = {
  columns: DataTableColumn<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  loading?: boolean;
  skeletonRows?: number;
  emptyState?: React.ReactNode;
  onRowClick?: (row: T) => void;
  className?: string;
  /** Client-side sorting only. No endpoint accepts a sort parameter. */
  sortable?: boolean;
};

/**
 * Shared list primitive: TanStack Table for the row model, a hand-rolled shell
 * so the responsive stacked-card layout stays under our control.
 * There is deliberately no paginator — no list endpoint has pagination.
 */
export function DataTable<T>({
  columns,
  rows,
  rowKey,
  loading,
  skeletonRows = 5,
  emptyState,
  onRowClick,
  className,
  sortable = false,
}: DataTableProps<T>) {
  const [sorting, setSorting] = React.useState<SortingState>([]);

  const data = React.useMemo(() => rows, [rows]);

  const columnDefs = React.useMemo<ColumnDef<T>[]>(
    () =>
      columns.map((column) => ({
        id: column.id,
        accessorFn: (row) => String(column.cell(row) ?? ""),
        header: column.header,
        cell: ({ row }) => column.cell(row.original),
        enableSorting: sortable,
      })),
    [columns, sortable],
  );

  const table = useReactTable({
    data,
    columns: columnDefs,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
  });

  if (!loading && rows.length === 0 && emptyState) {
    return <div className={className}>{emptyState}</div>;
  }

  return (
    <div className={className}>
      {/* Desktop / tablet */}
      <div className="hidden overflow-hidden rounded-md border border-subtle bg-surface md:block">
        <table className="w-full border-collapse text-left">
          <thead className="bg-surface">
            <tr className="border-b border-subtle">
              {columns.map((column) => (
                <th
                  key={column.id}
                  scope="col"
                  className={cn(
                    "px-4 py-3 text-xs font-medium text-tertiary",
                    column.secondary && "max-[1024px]:hidden",
                    column.align === "right" && "text-right",
                    column.headerClassName,
                  )}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: skeletonRows }).map((_, i) => (
                  <tr key={`sk-${i}`} className="border-b border-subtle last:border-0">
                    {columns.map((column) => (
                      <td
                        key={column.id}
                        className={cn(
                          "px-4 py-3",
                          column.secondary && "max-[1024px]:hidden",
                        )}
                      >
                        <Skeleton width={column.primary ? "60%" : "40%"} height={14} />
                      </td>
                    ))}
                  </tr>
                ))
              : table.getRowModel().rows.map((row) => (
                  <tr
                    key={rowKey(row.original)}
                    onClick={onRowClick ? () => onRowClick(row.original) : undefined}
                    className={cn(
                      "border-b border-subtle transition-colors last:border-0",
                      onRowClick && "cursor-pointer hover:bg-surface-hover",
                    )}
                  >
                    {row.getVisibleCells().map((cell) => {
                      const column = columns.find((c) => c.id === cell.column.id);
                      return (
                        <td
                          key={cell.column.id}
                          className={cn(
                            "px-4 py-3 align-middle text-base text-primary",
                            column?.secondary && "max-[1024px]:hidden",
                            column?.align === "right" && "text-right",
                            column?.cellClassName,
                          )}
                        >
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </td>
                      );
                    })}
                  </tr>
                ))}
          </tbody>
        </table>
      </div>

      {/* Mobile — each row becomes a bordered card with column labels as captions */}
      <div className="flex flex-col gap-3 md:hidden">
        {loading
          ? Array.from({ length: skeletonRows }).map((_, i) => (
              <div
                key={`msk-${i}`}
                className="rounded-md border border-subtle bg-surface p-4"
              >
                <Skeleton width="60%" height={16} />
                <Skeleton rows={2} height={12} className="mt-3" />
              </div>
            ))
          : rows.map((row) => {
              const primary = columns.find((c) => c.primary) ?? columns[0];
              return (
                <div
                  key={rowKey(row)}
                  onClick={onRowClick ? () => onRowClick(row) : undefined}
                  className={cn(
                    "rounded-md border border-subtle bg-surface p-4",
                    onRowClick && "cursor-pointer",
                  )}
                >
                  <div className="text-base font-medium text-primary">
                    {primary?.cell(row)}
                  </div>
                  <dl className="mt-3 flex flex-col gap-2">
                    {columns
                      .filter((c) => c.id !== primary?.id)
                      .map((column) => (
                        <div
                          key={column.id}
                          className="flex items-start justify-between gap-3"
                        >
                          <dt className="shrink-0 text-2xs text-tertiary">
                            {column.header}
                          </dt>
                          <dd className="min-w-0 text-right text-sm text-secondary">
                            {column.cell(row)}
                          </dd>
                        </div>
                      ))}
                  </dl>
                </div>
              );
            })}
      </div>
    </div>
  );
}