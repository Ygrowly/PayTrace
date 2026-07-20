import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "PayTrace",
  description:
    "Payment conversion anomaly attribution and diagnosis agent. (M0a skeleton)",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
