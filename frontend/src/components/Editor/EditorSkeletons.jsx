import React from 'react';

/**
 * Shimmering placeholder blocks.
 *
 * These render the *shape* of the content that is coming, not a spinner. On a
 * slow connection the document panel used to be a single centred spinner on an
 * empty white area, which read as "broken/empty document" and then snapped into
 * a wall of text. A skeleton keeps the layout stable and makes the wait legible.
 */

const Bar = ({ className = '', style }) => (
  <div className={`rd-skeleton rounded-md ${className}`} style={style} />
);

/** Stand-in for the interactive DOCX canvas: header zone, body, footer zone. */
export const DocumentSkeleton = () => (
  <div className="flex-grow overflow-hidden max-h-[560px] rounded-xl bg-slate-200/60 p-4 sm:p-6">
    <div className="bg-white shadow-xl shadow-slate-300/60 rounded-sm max-w-[680px] mx-auto min-h-[700px] p-8 sm:p-12 flex flex-col">
      <div className="text-center pb-2.5 mb-4 border-b-2 border-dashed border-slate-100">
        <Bar className="h-2.5 w-1/3 mx-auto" />
      </div>

      <div className="flex-grow space-y-5" aria-hidden="true">
        {[92, 100, 78, 95, 60, 88, 100, 72].map((width, i) => (
          <div key={i} className="space-y-2">
            <Bar className="h-2.5" style={{ width: `${width}%` }} />
            {i % 3 === 1 && (
              <div className="rounded-lg border border-slate-100 overflow-hidden">
                <div className="flex">
                  <div className="flex-1 border-r border-slate-100">
                    <div className="px-2 py-1.5 space-y-1.5">
                      <Bar className="h-2 w-1/2" />
                      <Bar className="h-2 w-4/5" />
                    </div>
                  </div>
                  <div className="flex-[2]">
                    <div className="px-2 py-1.5 space-y-1.5">
                      <Bar className="h-2 w-11/12" />
                      <Bar className="h-2 w-3/4" />
                    </div>
                  </div>
                </div>
                <div className="flex border-t border-slate-100">
                  <div className="flex-1 border-r border-slate-100 px-2 py-1.5">
                    <Bar className="h-2 w-2/3" />
                  </div>
                  <div className="flex-[2] px-2 py-1.5">
                    <Bar className="h-2 w-10/12" />
                  </div>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="text-center pt-2.5 mt-4 border-t-2 border-dashed border-slate-100">
        <Bar className="h-2.5 w-1/4 mx-auto" />
      </div>
    </div>
  </div>
);

/** Stand-in for the rendered-PDF iframe, which is a tall white page. */
export const PreviewSkeleton = () => (
  <div className="w-full bg-slate-100 rounded-lg border border-slate-200 overflow-hidden">
    <div className="mx-auto bg-white shadow-lg shadow-slate-300/60 max-w-[720px] px-8 sm:px-14 py-10 min-h-[560px] space-y-4">
      <div className="h-5 w-2/5 rounded-md rd-skeleton" />
      <div className="h-2.5 w-full rounded-md rd-skeleton" />
      <div className="h-2.5 w-11/12 rounded-md rd-skeleton" />
      <div className="h-2.5 w-4/5 rounded-md rd-skeleton" />
      <div className="h-40 w-full rounded-lg rd-skeleton my-6" />
      <div className="h-2.5 w-full rounded-md rd-skeleton" />
      <div className="h-2.5 w-10/12 rounded-md rd-skeleton" />
      <div className="h-2.5 w-full rounded-md rd-skeleton" />
      <div className="h-2.5 w-3/5 rounded-md rd-skeleton" />
    </div>
  </div>
);

/** Placeholder rows for the dashboard document table. */
export const DocumentListSkeleton = ({ rows = 4 }) => (
  <div className="overflow-hidden border border-borderline/80 rounded-3xl bg-white/80 backdrop-blur-xl shadow-card">
    <div className="overflow-x-auto">
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="bg-slate-50/80 border-b border-borderline/60">
            {['Document Name', 'Type', 'Pipeline Progress', 'Uploaded', 'Actions'].map((label) => (
              <th key={label} className="p-4 sm:px-6 text-xs font-bold uppercase tracking-wider text-secondary">
                {label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-borderline/40">
          {Array.from({ length: rows }).map((_, i) => (
            <tr key={i} className="animate-in fade-in duration-300" style={{ animationDelay: `${i * 90}ms` }}>
              <td className="p-4 sm:px-6">
                <div className="flex items-center gap-3.5">
                  <div className="p-2.5 rounded-2xl shrink-0">
                    <div className="w-5 h-5 rounded-md rd-skeleton" />
                  </div>
                  <div className="min-w-0 flex-1 space-y-1.5">
                    <div className="h-3 rounded rd-skeleton" style={{ width: `${55 + ((i * 13) % 35)}%` }} />
                    <div className="h-2 w-24 rounded rd-skeleton" />
                  </div>
                </div>
              </td>
              <td className="p-4">
                <div className="h-5 w-14 rounded-full rd-skeleton" />
              </td>
              <td className="p-4">
                <div className="space-y-2 max-w-[160px]">
                  <div className="h-2.5 w-3/4 rounded rd-skeleton" />
                  <div className="w-full h-2 rounded-full rd-skeleton" />
                </div>
              </td>
              <td className="p-4">
                <div className="h-3 w-20 rounded rd-skeleton" />
              </td>
              <td className="p-4 sm:px-6">
                <div className="flex justify-end gap-2">
                  <div className="h-7 w-20 rounded-xl rd-skeleton" />
                  <div className="h-8 w-8 rounded-xl rd-skeleton" />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);

/** Small inline shimmer used for the upload drop-zone while bytes are in flight. */
export const UploadProgressSkeleton = ({ progress = 0, label = 'Uploading' }) => (
  <div className="w-full max-w-xs space-y-2">
    <div className="flex items-center justify-between text-[11px] font-bold text-slate-500">
      <span>{label}</span>
      <span>{Math.round(progress)}%</span>
    </div>
    <div className="w-full h-1.5 rounded-full bg-slate-200 overflow-hidden">
      <div
        className="h-full rounded-full bg-gradient-to-r from-brand-500 to-indigo-600 transition-[width] duration-200 ease-out"
        style={{ width: `${Math.max(4, progress)}%` }}
      />
    </div>
  </div>
);
