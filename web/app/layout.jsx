import Script from "next/script";
import "./globals.css";

const GA_ID = "G-91M4529HE7";
const TOOL_NAME = "spm-calculator";

export const metadata = {
  title: "SPM threshold calculator | PolicyEngine",
  description:
    "Calculate Supplemental Poverty Measure thresholds across metros, states, counties, and congressional districts.",
  icons: { icon: "/favicon.svg" },
};

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap"
          rel="stylesheet"
        />
        <Script
          src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`}
          strategy="afterInteractive"
        />
        <Script id="gtag-init" strategy="afterInteractive">
          {`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('config', '${GA_ID}', { tool_name: '${TOOL_NAME}' });
          `}
        </Script>
      </head>
      <body>{children}</body>
    </html>
  );
}
