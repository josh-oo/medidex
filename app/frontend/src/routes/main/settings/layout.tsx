import { Suspense, useState, type ComponentType } from "react";
import { Outlet, useLocation } from "react-router-dom";
import { ChevronRight, PanelLeft, UserRound, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useExtensionRegistry } from "@/context/extension-registry-context";
import { useAuthStore } from "@/hooks/use-auth";
import { PageLink } from "@/lib/page-transition";
import { cn } from "@/lib/utils";

interface NavItem {
  path: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
}

interface NavGroup {
  label: string;
  items: NavItem[];
}

// The account first, then the sections of the extensions; administrators also get the users and the admin-only sections.
function useNavGroups(): NavGroup[] {
  const { settingsSections } = useExtensionRegistry();
  const isAdmin = useAuthStore((s) => s.user?.isAdmin ?? false);
  const groups: NavGroup[] = [
    {
      label: "Personal",
      items: [
        { path: "account", label: "Account", icon: UserRound },
        ...settingsSections.filter((section) => !section.adminOnly),
      ],
    },
  ];
  if (isAdmin) {
    groups.push({
      label: "Administration",
      items: [
        { path: "users", label: "Users", icon: Users },
        ...settingsSections.filter((section) => section.adminOnly),
      ],
    });
  }
  return groups;
}

const sectionOf = (pathname: string) => pathname.split("/").filter(Boolean)[1];

function SettingsNav({ groups, current, onNavigate }: { groups: NavGroup[]; current?: string; onNavigate?: () => void }) {
  return (
    <nav aria-label="Settings" className="space-y-5">
      {groups.map((group) => (
        <div key={group.label}>
          <p className="px-3 pb-1.5 text-xs font-medium text-muted-foreground">{group.label}</p>
          <ul className="space-y-0.5">
            {group.items.map(({ path, label, icon: Icon }) => {
              const active = path === current;
              return (
                <li key={path}>
                  <PageLink
                    to={`/settings/${path}`}
                    onClick={onNavigate}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                      active
                        ? "bg-accent font-medium text-accent-foreground"
                        : "text-muted-foreground hover:bg-accent/60 hover:text-foreground"
                    )}
                  >
                    <Icon className="h-4 w-4 shrink-0" />
                    {label}
                  </PageLink>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

/**
 * The settings: their sections listed on the left (on a narrow screen in a drawer from the left) and the open one on
 * the right. All of /settings is one page (lib/page-transition.tsx), so switching sections keeps the navigation.
 */
export default function SettingsLayout() {
  const { pathname } = useLocation();
  const groups = useNavGroups();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const current = sectionOf(pathname);
  const currentLabel = groups.flatMap((group) => group.items).find((item) => item.path === current)?.label;

  return (
    <div className="flex min-h-0 flex-1">
      <aside className="hidden w-60 shrink-0 overflow-y-auto border-r bg-muted/30 px-3 py-6 md:block">
        <h2 className="px-3 pb-4 text-lg font-semibold tracking-tight">Settings</h2>
        <SettingsNav groups={groups} current={current} />
      </aside>

      {/* The app layout clips overflow, so the section scrolls itself. */}
      <div className="min-h-0 min-w-0 flex-1 overflow-y-auto">
        <div className="sticky top-0 z-10 border-b bg-background/95 px-2 py-1.5 backdrop-blur md:hidden">
          <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="sm" className="gap-2">
                <PanelLeft className="h-4 w-4" />
                Settings
                {currentLabel && (
                  <>
                    <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                    <span className="font-normal text-muted-foreground">{currentLabel}</span>
                  </>
                )}
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 gap-2 px-3">
              <SheetHeader className="px-3">
                <SheetTitle>Settings</SheetTitle>
              </SheetHeader>
              <SettingsNav groups={groups} current={current} onNavigate={() => setDrawerOpen(false)} />
            </SheetContent>
          </Sheet>
        </div>

        <div className="mx-auto w-full max-w-5xl space-y-6 px-4 pb-10 pt-4 md:px-8 md:pt-6">
          {/* The sections are lazy chunks: while one loads the navigation stays, and the section is blank (no spinner). */}
          <Suspense fallback={null}>
            <Outlet />
          </Suspense>
        </div>
      </div>
    </div>
  );
}
