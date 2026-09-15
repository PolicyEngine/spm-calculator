"use client";

import { useEffect, useState } from "react";

import { calculatorUrl, paperPageUrl } from "@/src/paperVersion";

export const PACKAGE_URL = "https://pypi.org/project/spm-calculator/";
export const CODE_URL = "https://github.com/PolicyEngine/spm-calculator";

export const TOOL_LINKS = [
  { id: "calculator", label: "Calculator", href: calculatorUrl, kind: "internal" },
  { id: "paper", label: "Paper", href: paperPageUrl, kind: "internal", primary: true },
  { id: "package", label: "Python package", href: PACKAGE_URL, kind: "external" },
  { id: "code", label: "Code", href: CODE_URL, kind: "external" },
];

const strip = (path) => path.replace(/\/+$/, "");

export function isActiveLink(pathname, link) {
  if (!pathname || link.kind !== "internal") return false;
  const current = strip(pathname);
  const target = strip(link.href);
  if (target === strip(calculatorUrl)) return current === target;
  return current === target || current.startsWith(`${target}/`);
}

const LINK_BASE =
  "inline-flex items-center rounded-full px-3 py-1.5 text-sm font-medium no-underline transition-colors";

function linkClassName(link, active) {
  if (link.primary) {
    return `${LINK_BASE} bg-primary text-primary-foreground hover:bg-primary/90`;
  }
  if (active) return `${LINK_BASE} bg-muted text-foreground`;
  return `${LINK_BASE} text-muted-foreground hover:bg-muted hover:text-foreground`;
}

/** Tool-level navigation under the PolicyEngine site header: the calculator,
 * the methods paper (always the filled action, as PolicyBench presents its
 * paper), the published package and the source. Active state comes from the
 * browser path so the static export needs no router. */
export default function ToolHeader() {
  const [pathname, setPathname] = useState("");
  useEffect(() => {
    setPathname(window.location.pathname);
  }, []);
  return (
    <div data-testid="tool-header" className="border-b border-border bg-card">
      <nav
        aria-label="SPM Threshold Calculator"
        className="mx-auto flex w-full max-w-7xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3 sm:px-6 lg:px-8"
      >
        <a
          href={calculatorUrl}
          className="text-sm font-semibold text-foreground no-underline"
        >
          SPM Threshold Calculator{" "}
          <span className="font-normal text-muted-foreground">by PolicyEngine</span>
        </a>
        <ul className="flex flex-wrap items-center gap-2">
          {TOOL_LINKS.map((link) => {
            const active = isActiveLink(pathname, link);
            const external = link.kind === "external";
            return (
              <li key={link.id}>
                <a
                  href={link.href}
                  className={linkClassName(link, active)}
                  aria-current={active ? "page" : undefined}
                  data-tool-link={link.id}
                  {...(external
                    ? { target: "_blank", rel: "noopener noreferrer" }
                    : {})}
                >
                  {link.label}
                </a>
              </li>
            );
          })}
        </ul>
      </nav>
    </div>
  );
}
