import React from 'react';
import { FileText } from 'lucide-react';
import { LegalPageLayout } from './LegalPageLayout';

export const TermsOfService = ({ onNavigate }) => {
  return (
    <LegalPageLayout
      active="terms"
      icon={FileText}
      title="Terms of Service"
      description="The rules for using RapidDoc, your responsibilities, and the limits of the service."
      onNavigate={onNavigate}
    >
      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">1. Acceptance of these terms</h2>
        <p className="text-slate-700 leading-relaxed">
          By creating an account or using RapidDoc, you agree to these Terms of Service and our Privacy Policy.
          If you do not agree, do not use the service. If you use RapidDoc on behalf of an organization, you
          confirm that you have authority to accept these terms for that organization.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">2. Accounts and eligibility</h2>
        <p className="text-slate-700 leading-relaxed">
          You must provide accurate account information, keep your password confidential, and notify us promptly
          of unauthorized access. You are responsible for activity performed through your account. You must be
          old enough to enter a binding agreement in your jurisdiction.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">3. Acceptable use</h2>
        <p className="text-slate-700 leading-relaxed">You agree not to:</p>
        <ul className="list-disc pl-6 space-y-2 text-slate-700">
          <li>Upload content you do not own or lack permission to process.</li>
          <li>Use the service for unlawful, fraudulent, harassing, or harmful activity.</li>
          <li>Attempt to bypass authentication, access another user&apos;s documents, or disrupt the service.</li>
          <li>Probe, scan, or test the service for vulnerabilities without written authorization.</li>
          <li>Reverse engineer or copy the service except where permitted by law.</li>
        </ul>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">4. Your content and intellectual property</h2>
        <p className="text-slate-700 leading-relaxed">
          You retain ownership of the documents and content you upload. You grant RapidDoc a limited license to
          store, process, and transmit that content solely to provide the features you request. The RapidDoc
          name, interface, software, and branding remain our property or that of our licensors.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">5. AI-generated output</h2>
        <p className="text-slate-700 leading-relaxed">
          Summaries, translations, study notes, keywords, questions, and other AI output may contain errors or
          omissions. You are responsible for reviewing output before relying on it, submitting it, or publishing
          it. AI output is not legal, medical, financial, or other professional advice.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">6. Service availability and file limits</h2>
        <p className="text-slate-700 leading-relaxed">
          We work to keep RapidDoc available, but the service is provided on an &quot;as available&quot; basis and
          may be interrupted for maintenance or security. Supported uploads may be limited by file type and size,
          including a 15 MB limit per file. Features may change or be withdrawn.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">7. Third-party services</h2>
        <p className="text-slate-700 leading-relaxed">
          Some features may rely on third-party AI, infrastructure, or email providers. Those providers are
          governed by their own terms and privacy policies. We are not responsible for third-party services
          outside our control.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">8. Suspension and termination</h2>
        <p className="text-slate-700 leading-relaxed">
          You may stop using RapidDoc at any time. We may suspend or terminate access when these terms are
          violated, when required by law, or when necessary to protect users or the service. On termination,
          your right to use the service ends, but obligations that by their nature survive will continue.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">9. Disclaimers</h2>
        <p className="text-slate-700 leading-relaxed">
          To the maximum extent permitted by law, RapidDoc is provided without warranties of any kind, whether
          express or implied, including merchantability, fitness for a particular purpose, and non-infringement.
          We do not guarantee that the service will be uninterrupted, error-free, or that any output will be
          accurate or suitable for your purpose.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">10. Limitation of liability</h2>
        <p className="text-slate-700 leading-relaxed">
          To the maximum extent permitted by law, RapidDoc and its suppliers will not be liable for indirect,
          incidental, special, consequential, or punitive damages, or for loss of data, profits, revenue, or
          business opportunity arising from your use of or inability to use the service.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">11. Changes to these terms</h2>
        <p className="text-slate-700 leading-relaxed">
          We may update these terms from time to time. The updated version will be posted here with a new date.
          Continued use of RapidDoc after an update means you accept the revised terms.
        </p>
      </section>

      <section className="rounded-2xl border border-blue-100 bg-blue-50/60 p-5">
        <h2 className="text-xl font-bold text-slate-900 mb-2">12. Contact</h2>
        <p className="text-slate-700 leading-relaxed">
          Questions about these terms? Email{' '}
          <a href="mailto:support@rapiddoc.ai" className="font-bold text-brand-600 hover:text-brand-700">
            support@rapiddoc.ai
          </a>{' '}
          or contact us through the{' '}
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

export default TermsOfService;
