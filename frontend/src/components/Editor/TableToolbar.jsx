import React from 'react';
import { 
  Plus, Trash2, ArrowUp, ArrowDown, ArrowLeft, ArrowRight, Table as TableIcon 
} from 'lucide-react';

export const TableToolbar = ({
  tableIndex,
  selectedRow,
  selectedCol,
  onAddRow,
  onDeleteRow,
  onAddColumn,
  onDeleteColumn,
  onDeleteTable,
  loading = false,
}) => {
  return (
    <div className="flex flex-wrap items-center gap-1.5 p-1.5 bg-white border border-slate-200/90 rounded-2xl shadow-md text-xs select-none animate-in fade-in slide-in-from-top-1 duration-150">
      <div className="flex items-center gap-1 px-2 py-0.5 bg-blue-50 text-blue-700 rounded-lg font-bold text-[10px]">
        <TableIcon className="w-3 h-3" />
        <span>Table {tableIndex + 1}</span>
      </div>

      <div className="w-px h-4 bg-slate-200 mx-0.5" />

      {/* Row operations */}
      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={loading}
          onClick={() => onAddRow('above', selectedRow)}
          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-50 hover:bg-slate-100 text-slate-700 font-semibold text-[10px] transition border border-slate-200/60 cursor-pointer disabled:opacity-50"
          title="Add Row Above"
        >
          <ArrowUp className="w-3 h-3 text-emerald-600" />
          <span>+ Row Above</span>
        </button>

        <button
          type="button"
          disabled={loading}
          onClick={() => onAddRow('below', selectedRow)}
          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-50 hover:bg-slate-100 text-slate-700 font-semibold text-[10px] transition border border-slate-200/60 cursor-pointer disabled:opacity-50"
          title="Add Row Below"
        >
          <ArrowDown className="w-3 h-3 text-emerald-600" />
          <span>+ Row Below</span>
        </button>

        <button
          type="button"
          disabled={loading}
          onClick={() => onDeleteRow(selectedRow)}
          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-red-50/70 hover:bg-red-100 text-red-700 font-semibold text-[10px] transition border border-red-200/60 cursor-pointer disabled:opacity-50"
          title="Delete Current Row"
        >
          <Trash2 className="w-3 h-3" />
          <span>Del Row</span>
        </button>
      </div>

      <div className="w-px h-4 bg-slate-200 mx-0.5" />

      {/* Column operations */}
      <div className="flex items-center gap-1">
        <button
          type="button"
          disabled={loading}
          onClick={() => onAddColumn('left', selectedCol)}
          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-50 hover:bg-slate-100 text-slate-700 font-semibold text-[10px] transition border border-slate-200/60 cursor-pointer disabled:opacity-50"
          title="Add Column Left"
        >
          <ArrowLeft className="w-3 h-3 text-blue-600" />
          <span>+ Col Left</span>
        </button>

        <button
          type="button"
          disabled={loading}
          onClick={() => onAddColumn('right', selectedCol)}
          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-slate-50 hover:bg-slate-100 text-slate-700 font-semibold text-[10px] transition border border-slate-200/60 cursor-pointer disabled:opacity-50"
          title="Add Column Right"
        >
          <ArrowRight className="w-3 h-3 text-blue-600" />
          <span>+ Col Right</span>
        </button>

        <button
          type="button"
          disabled={loading}
          onClick={() => onDeleteColumn(selectedCol)}
          className="flex items-center gap-1 px-2 py-1 rounded-lg bg-red-50/70 hover:bg-red-100 text-red-700 font-semibold text-[10px] transition border border-red-200/60 cursor-pointer disabled:opacity-50"
          title="Delete Current Column"
        >
          <Trash2 className="w-3 h-3" />
          <span>Del Col</span>
        </button>
      </div>

      <div className="w-px h-4 bg-slate-200 mx-0.5" />

      {/* Delete whole table */}
      <button
        type="button"
        disabled={loading}
        onClick={onDeleteTable}
        className="p-1 rounded-lg hover:bg-red-100 text-red-500 hover:text-red-700 transition cursor-pointer disabled:opacity-50"
        title="Delete Table"
      >
        <Trash2 className="w-3.5 h-3.5" />
      </button>
    </div>
  );
};
