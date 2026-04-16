import "./globals.css";

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
      </head>
      <body>{children}</body>
    </html>
  );
}
