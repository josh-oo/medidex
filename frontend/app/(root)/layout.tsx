import { AppHeader } from "@/components/header/app-header";

export default function Layout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <div className="h-full overflow-hidden">
      <AppHeader />
      <main className="pt-14 h-full overflow-hidden flex flex-col">
        {children}
      </main>
    </div>
  );
}
