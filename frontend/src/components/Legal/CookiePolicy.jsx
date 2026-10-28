import React from 'react';
import { Cookie } from 'lucide-react';
import { LegalPageLayout } from './LegalPageLayout';

export const CookiePolicy = ({ onNavigate }) => {
  return (
    <LegalPageLayout
      active="cookies"
      icon={Cookie}
      title="Cookie Policy"
      description="How RapidDoc uses cookies and similar browser storage, why we use them, and how you can control them."
      onNavigate={onNavigate}
    >
      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">1. Scope</h2>
        <p className="text-slate-700 leading-relaxed">
          This Cookie Policy explains how RapidDoc uses cookies and similar technologies such as local storage
          and session storage. It should be read alongside our Privacy Policy.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">2. What cookies and local storage are</h2>
        <p className="text-slate-700 leading-relaxed">
          Cookies are small text files placed in your browser. Local storage works in a similar way but stores
          data directly in your browser until it is cleared. These technologies can help a site remember your
          session and preferences.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">3. Storage we use</h2>
        <div className="overflow-hidden rounded-xl border border-slate-200">
          <table className="w-full text-left text-xs sm:text-sm">
            <thead className="bg-slate-50 text-slate-700">
              <tr>
                <th className="px-4 py-3 font-bold">Type</th>
                <th className="px-4 py-3 font-bold">Purpose</th>
                <th className="px-4 py-3 font-bold">Required</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-slate-600">
              <tr>
                <td className="px-4 py-3 font-semibold text-slate-800">Authentication token</td>
                <td className="px-4 py-3">Keeps you signed in and authorizes requests to your documents.</td>
                <td className="px-4 py-3">Yes</td>
              </tr>
              <tr>
                <td className="px-4 py-3 font-semibold text-slate-800">Unsaved editor state</td>
                <td className="px-4 py-3">Held in the current tab&apos;s memory until you save or leave the page.</td>
                <td className="px-4 py-3">Yes</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-slate-700 leading-relaxed mt-3">
          The authentication token is stored in browser local storage under the key <code>token</code>. Signing
          out removes it.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">4. What we do not use</h2>
        <p className="text-slate-700 leading-relaxed">
          RapidDoc does not currently use advertising cookies, cross-site tracking cookies, or third-party
          analytics cookies. If this changes, we will update this policy and, where required, request consent.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">5. Third-party services</h2>
        <p className="text-slate-700 leading-relaxed">
          Features that call an external AI provider may transmit the content required for that feature. Those
          providers may use their own storage or security technologies on their systems. We do not control
          third-party cookies that are set outside the RapidDoc application.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">6. Managing browser storage</h2>
        <p className="text-slate-700 leading-relaxed">
          You can clear or block cookies and local storage through your browser settings. Blocking essential
          storage may sign you out or prevent the editor from working correctly. Clearing site data does not
          delete documents already stored in your RapidDoc account.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">7. Do Not Track</h2>
        <p className="text-slate-700 leading-relaxed">
          Because RapidDoc does not currently use cross-site tracking or advertising cookies, there is no
          separate tracking to disable. Your browser&apos;s Do Not Track signal does not change the essential
          storage used to keep you signed in.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">8. Changes to this policy</h2>
        <p className="text-slate-700 leading-relaxed">
          We may update this Cookie Policy when our use of storage changes. The revised policy will be posted
          here with a new update date.
        </p>
      </section>

      <section className="rounded-2xl border border-blue-100 bg-blue-50/60 p-5">
        <h2 className="text-xl font-bold text-slate-900 mb-2">9. Contact</h2>
        <p className="text-slate-700 leading-relaxed">
          If you have questions about cookies or browser storage, email{' '}
          <a href="mailto:support@rapiddoc.ai" className="font-bold text-brand-600 hover:text-brand-700">
            support@rapiddoc.ai
          </a>{' '}
          or use the{' '}
          <button
            type="button"
            onClick={() => onNavigate('help')}
            className="font-bold text-brand-600 hover:text-brand-700 underline underline-offset-2"
          >
            Help Center
          </button>
          .
        </p>
      </section>
    </LegalPageLayout>
  );
};

export default CookiePolicy;
