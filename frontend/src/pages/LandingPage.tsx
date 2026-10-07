import { Link } from "react-router-dom";
import { ParticleField } from "@/components/landing/ParticleField";
import { Reveal } from "@/components/landing/Reveal";
import { useAuth } from "@/state/auth";
import "@/styles/landing.css";

const FEATURES = [
  {
    icon: (
      <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      </svg>
    ),
    title: "Tax Assistant",
    text: "Grounded answers on Income Tax, Sales Tax, Federal Excise and Customs — with section citations from 107 FBR source documents.",
    href: "/personal/assistant",
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <rect x="4" y="2" width="16" height="20" rx="2" />
        <line x1="8" x2="16" y1="6" y2="6" />
        <line x1="8" x2="8" y1="11" y2="11" />
        <line x1="12" x2="12" y1="11" y2="11" />
        <line x1="16" x2="16" y1="11" y2="11" />
        <line x1="8" x2="8" y1="15" y2="15" />
        <line x1="12" x2="12" y1="15" y2="15" />
        <line x1="16" x2="16" y1="15" y2="15" />
        <line x1="8" x2="16" y1="19" y2="19" />
      </svg>
    ),
    title: "Tax Calculator",
    text: "11 calculation modules — salary, business, sales tax, withholding, capital gains, property, dividends and customs duty.",
    href: "/personal/calculator",
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14,2 14,8 20,8" />
        <line x1="16" x2="8" y1="13" y2="13" />
        <line x1="16" x2="8" y1="17" y2="17" />
      </svg>
    ),
    title: "Notice Analyzer",
    text: "Understand 30+ FBR notice types with deadlines, action plans and appeal guidance — never miss a response window.",
    href: "/personal/notices",
  },
  {
    icon: (
      <svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
        <rect width="18" height="18" x="3" y="4" rx="2" ry="2" />
        <line x1="16" x2="16" y1="2" y2="6" />
        <line x1="8" x2="8" y1="2" y2="6" />
        <line x1="3" x2="21" y1="10" y2="10" />
      </svg>
    ),
    title: "Compliance Calendar",
    text: "FY 2024–27 filing deadlines, reminders and a live compliance score for individuals and businesses.",
    href: "/personal/calendar",
  },
];

const STEPS = [
  {
    n: "1",
    title: "Ask or upload",
    text: "Type a tax question, run a calculation, or upload an FBR notice or invoice.",
  },
  {
    n: "2",
    title: "Get grounded answers",
    text: "The 9-agent router pulls evidence from verified FBR law — every answer carries citations.",
  },
  {
    n: "3",
    title: "Stay compliant",
    text: "Track deadlines, monitor notices and keep your health score green, all year.",
  },
];

export function LandingPage() {
  const session = useAuth((state) => state.token);
  return (
    <div className="landing" data-testid="landing-page">
      <nav className="landing-nav" aria-label="Main navigation">
        <Link to="/" className="landing-brand" aria-label="FBR Assistant home">
          <span className="landing-brand__seal">FBR</span>
          <span><strong>FBR</strong> Assistant <small>Tax &amp; Compliance</small></span>
        </Link>
        <div className="landing-nav__links">
          <a href="#capabilities">Capabilities</a>
          <a href="#method">How it works</a>
          <a href="#contact">Contact</a>
        </div>
        {session ? (
          <Link to="/personal/overview" className="landing-nav__account">Open workspace <span>↗</span></Link>
        ) : (
          <Link to="/login" className="landing-nav__account">Sign in <span>↗</span></Link>
        )}
      </nav>
      <section className="landing-hero" data-testid="landing-hero">
        <div className="landing-hero__aurora" aria-hidden />
        <ParticleField />
        <svg className="landing-hero__seal" viewBox="0 0 120 120" aria-hidden focusable="false">
          <circle cx="60" cy="60" r="56" fill="none" stroke="rgba(198,161,91,0.5)" strokeWidth="1" strokeDasharray="4 6" />
          <circle cx="60" cy="60" r="44" fill="none" stroke="rgba(198,161,91,0.3)" strokeWidth="1" />
          <path d="M66 34a26 26 0 1 0 0 52 30 30 0 1 1 0-52z" fill="rgba(198,161,91,0.55)" />
          <path d="M78 52l2.6 6.2 6.7.5-5.1 4.4 1.6 6.6-5.8-3.6-5.8 3.6 1.6-6.6-5.1-4.4 6.7-.5z" fill="rgba(198,161,91,0.8)" />
        </svg>
        <div className="landing-hero__inner">
          <p className="landing-hero__crest">Government of Pakistan — Federal Board of Revenue</p>
          <h1 className="landing-hero__title">FBR Tax &amp; Compliance Assistant</h1>
          <p className="landing-hero__sub">
            Grounded answers on Income Tax, Sales Tax, Federal Excise and Customs —
            backed by official FBR law, with calculators, notice analysis and compliance tracking.
          </p>
          <div className="landing-hero__ctas">
             <Link to={session ? "/personal/overview" : "/login"} className="landing-btn landing-btn--gold" data-testid="landing-cta-app">
               {session ? "Continue to workspace" : "Enter the assistant"}
            </Link>
             <Link to={session ? "/personal/settings" : "/login"} className="landing-btn landing-btn--outline" data-testid="landing-cta-login">
               {session ? "Account settings" : "Login"}
            </Link>
            <Link to="/business/overview" className="landing-btn landing-btn--ghost">
              For Business
            </Link>
          </div>
           <div className="landing-trust" aria-label="Platform highlights">
            <span><strong>107</strong> official FBR documents</span>
            <span aria-hidden>·</span>
            <span><strong>Cited</strong> answers only</span>
            <span aria-hidden>·</span>
            <span><strong>11</strong> tax calculators</span>
            <span aria-hidden>·</span>
            <span><strong>Personal + Business</strong> workspaces</span>
           </div>
         </div>
      </section>

             <Reveal>
      <section className="landing-proof" aria-label="Platform promise">
         <div className="landing-wrap landing-proof__inner">
           <div><span className="landing-proof__mark">01</span><strong>Official-source first</strong><span>Evidence before confidence.</span></div>
           <div><span className="landing-proof__mark">02</span><strong>Built for Pakistan</strong><span>FBR workflows, not generic tax chat.</span></div>
           <div><span className="landing-proof__mark">03</span><strong>Human-readable</strong><span>Clear actions, references and next steps.</span></div>
         </div>
       </section>

             </Reveal>

      <Reveal>
      <section className="landing-section landing-section--capabilities" id="capabilities" data-testid="landing-features" aria-label="Features">
         <div className="landing-wrap">
           <p className="landing-eyebrow">The compliance desk, rethought</p>
           <div className="landing-section__heading"><h2 className="landing-h2">One assistant for every tax task</h2><p>From a quick question to a complete compliance trail, keep the work in one calm, evidence-led place.</p></div>
           <div className="landing-grid">
            {FEATURES.map((f) => (
              <Link key={f.title} to={f.href} className="landing-card">
                <span className="landing-card__icon">{f.icon}</span>
                <h3 className="landing-card__title">{f.title}</h3>
                <p className="landing-card__text">{f.text}</p>
                <span className="landing-card__link">Open →</span>
              </Link>
            ))}
          </div>
        </div>
       </section>

             </Reveal>

      <Reveal>
      <section className="landing-showcase" aria-label="Workspace preview">
         <div className="landing-wrap landing-showcase__layout">
           <div className="landing-showcase__copy"><p className="landing-eyebrow">A clearer way to work</p><h2 className="landing-h2">Less searching.<br /><em>More certainty.</em></h2><p>Built around the rhythm of real tax work: understand the rule, calculate the impact, capture the evidence, and act before the deadline.</p><Link to={session ? "/personal/overview" : "/login"} className="landing-text-link">{session ? "Open your workspace" : "Create your workspace"} <span>→</span></Link></div>
           <div className="landing-dashboard" aria-label="Illustration of the assistant workspace"><div className="landing-dashboard__top"><span className="landing-dashboard__dot"></span><span>FBR / COMPLIANCE DESK</span><span className="landing-dashboard__date">TY 2025</span></div><div className="landing-dashboard__body"><div className="landing-dashboard__rail"><i></i><i></i><i></i><i></i></div><div className="landing-dashboard__main"><div className="landing-dashboard__line landing-dashboard__line--short"></div><div className="landing-dashboard__line"></div><div className="landing-dashboard__metrics"><div><small>COMPLIANCE SCORE</small><strong>86<span>/100</span></strong></div><div><small>NEXT DEADLINE</small><strong>12 <span>days</span></strong></div></div><div className="landing-dashboard__chart"><span></span><span></span><span></span><span></span><span></span><span></span><span></span></div></div></div><div className="landing-dashboard__stamp">VERIFIED<br /><small>FBR SOURCE INDEX</small></div></div>
         </div>
       </section>

            </Reveal>

      <Reveal>
      <section className="landing-section landing-section--alt" id="method" aria-label="How it works">
        <div className="landing-wrap">
          <p className="landing-eyebrow">How it works</p>
          <h2 className="landing-h2">From question to compliance in three steps</h2>
          <ol className="landing-steps">
            {STEPS.map((s) => (
              <li key={s.n} className="landing-step">
                <span className="landing-step__n">{s.n}</span>
                <h3 className="landing-step__title">{s.title}</h3>
                <p className="landing-step__text">{s.text}</p>
              </li>
            ))}
          </ol>
        </div>
       </section>

             </Reveal>

      <Reveal>
      <section className="landing-contact" id="contact" aria-label="Contact and help">
         <div className="landing-wrap">
            <p className="landing-eyebrow">Help &amp; contact</p>
            <div className="landing-contact__heading"><h2 className="landing-h2">Need help? Talk to us.</h2><p>Questions about your taxes, a notice, or your compliance score — start with the assistant or write to us directly.</p></div>
            <div className="landing-contact__grid">
              <a className="landing-contact__card" href="mailto:hello@fbrassistant.pk">
                <span className="landing-contact__label">Email us</span>
                <span className="landing-contact__value">hello@fbrassistant.pk</span>
                <span className="landing-contact__hint">We reply within 2 working days <span aria-hidden>↗</span></span>
              </a>
              <Link className="landing-contact__card" to="/personal/assistant">
                <span className="landing-contact__label">Ask the assistant</span>
                <span className="landing-contact__value">Get a grounded answer</span>
                <span className="landing-contact__hint">Cited from official FBR law <span aria-hidden>→</span></span>
              </Link>
              <Link className="landing-contact__card" to="/personal/overview">
                <span className="landing-contact__label">Open workspace</span>
                <span className="landing-contact__value">Continue your work</span>
                <span className="landing-contact__hint">Dashboard, deadlines &amp; health <span aria-hidden>→</span></span>
              </Link>
            </div>
         </div>
       </section>

            </Reveal>

      <footer className="landing-footer">
        <div className="landing-wrap">
          <div className="landing-footer__grid">
            <div className="landing-footer__brand">
              <span className="landing-brand__seal">FBR</span>
              <p className="landing-footer__tag"><strong>FBR</strong> Tax &amp; Compliance Assistant</p>
              <p className="landing-footer__note">Grounded tax guidance, calculators and compliance tracking for Pakistan.</p>
            </div>
            <nav className="landing-footer__col" aria-label="Product">
              <p className="landing-footer__head">Product</p>
              <Link to="/personal/assistant">Tax Assistant</Link>
              <Link to="/personal/calculator">Tax Calculator</Link>
              <Link to="/personal/notices">Notice Analyzer</Link>
              <Link to="/personal/calendar">Compliance Calendar</Link>
            </nav>
            <nav className="landing-footer__col" aria-label="Workspaces">
              <p className="landing-footer__head">Workspaces</p>
              <Link to="/personal/overview">Personal</Link>
              <Link to="/business/overview">Business</Link>
            </nav>
            <nav className="landing-footer__col" aria-label="Support">
              <p className="landing-footer__head">Support</p>
              <a href="#method">How it works</a>
              <a href="#contact">Contact</a>
              <a href="mailto:hello@fbrassistant.pk">hello@fbrassistant.pk</a>
            </nav>
          </div>
          <div className="landing-footer__row">
            <span>© 2026 FBR Tax &amp; Compliance Assistant</span>
            <span>
              <a href="#capabilities">Capabilities</a>
              {" · "}
              <a href="#contact">Contact</a>
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
