import {
  PAPER_AUTHORS,
  PAPER_REPO_URL,
  PAPER_REVISION,
  PAPER_REVISION_DATE,
  PAPER_TITLE,
  calculatorUrl,
  paperHtmlUrl,
  paperPdfUrl,
} from "@/src/paperVersion";

const SITE_URL = "https://www.policyengine.org/us/spm-calculator/paper";
const DESCRIPTION =
  "The methods paper behind the SPM Threshold Calculator: reconstructing published Supplemental Poverty Measure thresholds from public Consumer Expenditure microdata, and comparing projection rules whose 2020–2025 mean absolute errors range from 2.29 percent for CPI-U adjustment to 0.51 percent for replicated consumption growth.";

export const metadata = {
  title: `${PAPER_TITLE} | PolicyEngine`,
  description: DESCRIPTION,
  alternates: {
    canonical: SITE_URL,
  },
  openGraph: {
    title: `${PAPER_TITLE} | PolicyEngine`,
    description: DESCRIPTION,
    url: SITE_URL,
    siteName: "PolicyEngine",
    type: "article",
    locale: "en_US",
  },
  twitter: {
    card: "summary",
    title: `${PAPER_TITLE} | PolicyEngine`,
    description: DESCRIPTION,
    site: "@ThePolicyEngine",
  },
  robots: {
    index: true,
    follow: true,
  },
};

const PRIMARY_ACTION =
  "inline-flex items-center rounded-lg bg-primary px-4 py-2 text-sm font-medium text-primary-foreground no-underline transition-colors hover:bg-primary/90";
const SECONDARY_ACTION =
  "inline-flex items-center rounded-lg border border-border bg-card px-4 py-2 text-sm font-medium text-foreground no-underline transition-colors hover:bg-muted";

export default function PaperPage() {
  return (
    <main
      id="paper-top"
      className="mx-auto w-full max-w-5xl px-4 py-10 sm:px-6 lg:px-8"
    >
      <header className="space-y-4">
        <p className="text-xs font-semibold uppercase tracking-widest text-muted-foreground">
          Working paper
        </p>
        <h1 className="text-3xl font-semibold leading-tight text-foreground sm:text-4xl">
          {PAPER_TITLE}
        </h1>
        <p className="max-w-3xl text-base leading-7 text-muted-foreground">
          The paper reconstructs national Supplemental Poverty Measure
          thresholds from public Consumer Expenditure microdata. Every tenure
          and year from 2019 through 2025 lands within 2.8 percent of the
          published value, and most within 2 percent. It then compares four
          rules for projecting thresholds: over 2020 to 2025, adjusting the
          last published threshold by CPI-U gives a mean absolute error of
          2.29 percent, against 0.51 percent for replicated consumption growth.
          A 2025 nowcast committed to before BLS published, an equal blend of
          replicated growth and a composite price index, landed within 1.17
          percent of the published thresholds, where CPI-U adjustment was off
          by 2.58 percent. Embedded below is the manuscript rendered from
          commit {PAPER_REVISION}.
        </p>
        <p
          data-testid="paper-revision-pill"
          className="inline-flex items-center rounded-full border border-border bg-muted px-3 py-1 text-xs font-medium text-muted-foreground"
        >
          Revision {PAPER_REVISION} · {PAPER_REVISION_DATE} · {PAPER_AUTHORS}
        </p>
      </header>

      <nav
        aria-label="Paper actions"
        data-testid="paper-actions"
        className="mt-8 flex flex-wrap gap-3"
      >
        <a className={PRIMARY_ACTION} href={paperHtmlUrl}>
          Open standalone HTML
        </a>
        <a className={SECONDARY_ACTION} href={paperPdfUrl}>
          Download PDF
        </a>
        <a className={SECONDARY_ACTION} href={calculatorUrl}>
          Live calculator
        </a>
        <a
          className={SECONDARY_ACTION}
          href={PAPER_REPO_URL}
          target="_blank"
          rel="noopener noreferrer"
        >
          Code and artifacts
        </a>
      </nav>

      <div className="mt-8 overflow-hidden rounded-xl border border-border bg-card shadow-sm">
        <iframe
          data-testid="paper-embed"
          className="block w-full border-0"
          src={paperHtmlUrl}
          title={`${PAPER_TITLE} (manuscript)`}
          loading="lazy"
          sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox"
          referrerPolicy="same-origin"
          style={{
            height: "calc(100vh - 16rem)",
            minHeight: "720px",
            background: "#fff",
          }}
        />
      </div>

      <p className="mt-6 text-sm text-muted-foreground">
        <a className="underline" href="#paper-top">
          ↑ Back to top
        </a>{" "}
        ·{" "}
        <a className="underline" href={paperHtmlUrl}>
          Open manuscript in a new page
        </a>
      </p>
    </main>
  );
}
