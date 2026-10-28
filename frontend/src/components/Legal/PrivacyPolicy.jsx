import React from 'react';
import { Shield } from 'lucide-react';
import { LegalPageLayout } from './LegalPageLayout';

export const PrivacyPolicy = ({ onNavigate }) => {
  return (
    <LegalPageLayout
      active="privacy"
      icon={Shield}
      title="Privacy Policy"
      description="How RapidDoc collects, uses, stores, and protects your account information and documents."
      onNavigate={onNavigate}
    >
      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">1. Overview</h2>
        <p className="text-slate-700 leading-relaxed">
          This Privacy Policy explains what information RapidDoc collects, why we collect it, how it is used,
          and the choices available to you. It applies to the RapidDoc website, editor, AI tools, and related
          support services.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">2. Information we collect</h2>
        <p className="text-slate-700 leading-relaxed">We collect information you provide directly to us, including:</p>
        <ul className="list-disc pl-6 space-y-2 text-slate-700">
          <li>Account details such as your name, email address, and securely hashed password.</li>
          <li>Documents and files you upload for preview, editing, conversion, or AI-assisted processing.</li>
          <li>Support messages, issue reports, and the contact details you include with them.</li>
          <li>Basic technical and usage information needed to operate, secure, and troubleshoot the service.</li>
        </ul>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">3. How we use information</h2>
        <p className="text-slate-700 leading-relaxed">We use the information we collect to:</p>
        <ul className="list-disc pl-6 space-y-2 text-slate-700">
          <li>Create and authenticate your account and maintain your session.</li>
          <li>Store, display, edit, summarize, translate, and export the documents you choose to process.</li>
          <li>Generate the AI outputs you request, such as summaries, study notes, keywords, and questions.</li>
          <li>Respond to support requests, investigate issues, and improve reliability.</li>
          <li>Protect the service against abuse, unauthorized access, and security threats.</li>
        </ul>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">4. AI processing</h2>
        <p className="text-slate-700 leading-relaxed">
          RapidDoc may use locally hosted AI models and, when configured by the operator, third-party AI
          providers to process the text you submit. Only the content needed for the requested operation is
          sent for processing. We do not sell your documents or use them to train our own models.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">5. Cookies and local storage</h2>
        <p className="text-slate-700 leading-relaxed">
          We use browser storage to keep you signed in and to remember essential session information. We do
          not currently use advertising cookies or third-party analytics cookies. See our{' '}
          <button
            type="button"
            onClick={() => onNavigate('cookies')}
            className="font-bold text-brand-600 hover:text-brand-700 underline underline-offset-2"
          >
            Cookie Policy
          </button>{' '}
          for more detail.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">6. Document privacy and retention</h2>
        <p className="text-slate-700 leading-relaxed">
          Your documents remain your property. Uploaded files and their edited versions are stored so you can
          access them through your account. We retain them until you delete the document or your account, or
          until retention is no longer necessary for the service. Backup and security logs may persist for a
          limited period.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">7. Security</h2>
        <p className="text-slate-700 leading-relaxed">
          We use access controls, JWT authentication, and bcrypt password hashing to protect account data.
          Documents are associated with their owner and are not exposed to other users. No method of storage or
          transmission is completely secure, so you should avoid uploading information you are not authorized
          to process.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">8. Your rights and choices</h2>
        <p className="text-slate-700 leading-relaxed">Depending on your location, you may have the right to:</p>
        <ul className="list-disc pl-6 space-y-2 text-slate-700">
          <li>Access, correct, or update your account information.</li>
          <li>Delete documents you uploaded and request deletion of your account data.</li>
          <li>Request a copy of the personal information associated with your account.</li>
          <li>Object to or restrict certain processing, where applicable by law.</li>
        </ul>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">9. Children&apos;s privacy</h2>
        <p className="text-slate-700 leading-relaxed">
          RapidDoc is not directed to children under 13, and we do not knowingly collect personal information
          from children under 13. If you believe a child has provided us with personal information, contact us
          so we can remove it.
        </p>
      </section>

      <section>
        <h2 className="text-xl font-bold text-slate-900 mb-3">10. Changes to this policy</h2>
        <p className="text-slate-700 leading-relaxed">
          We may update this policy as the service changes. The revised version will be posted on this page with
          a new update date. Material changes may also be communicated through the service.
        </p>
      </section>

      <section className="rounded-2xl border border-blue-100 bg-blue-50/60 p-5">
        <h2 className="text-xl font-bold text-slate-900 mb-2">11. Contact us</h2>
        <p className="text-slate-700 leading-relaxed">
          For privacy questions or data requests, email{' '}
          <a href="mailto:support@rapiddoc.ai" className="font-bold text-brand-600 hover:text-brand-700">
            support@rapiddoc.ai
          </a>{' '}
          or use the issue form in our{' '}
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

export default PrivacyPolicy;
