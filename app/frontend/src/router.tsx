import { lazy, Suspense } from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Spinner } from "./components/ui/spinner";
import { useExtensionRegistry } from "./context/extension-registry-context";
import LoginPage from "./routes/auth/login/page";
import RegisterPage from "./routes/auth/register/page";
import PendingApprovalPage from "./routes/auth/pending-approval/page";
import RootLayout from "./routes/main/layout";

const HomePage = lazy(() => import("./routes/main/page"));
const UserManagementPage = lazy(() => import("./routes/main/user-management/page"));
const CurationPage = lazy(() => import("./routes/main/curation/page"));
const PdfUploadProjectLayout = lazy(() => import("./routes/main/pdf-upload/projectId/layout"));
const PdfUploadProjectPage = lazy(() => import("./routes/main/pdf-upload/projectId/page"));
const PdfUploadReportPage = lazy(() => import("./routes/main/pdf-upload/projectId/reportId/page"));
const ProjectsProjectLayout = lazy(() => import("./routes/main/projects/projectId/layout"));
const ProjectsProjectPage = lazy(() => import("./routes/main/projects/projectId/page"));
const ProjectsReportPage = lazy(() => import("./routes/main/projects/projectId/reportId/page"));
const ReviewProjectLayout = lazy(() => import("./routes/main/review/projectId/layout"));
const ReviewProjectPage = lazy(() => import("./routes/main/review/projectId/page"));
const ReviewReportPage = lazy(() => import("./routes/main/review/projectId/reportId/page"));

const RouteFallback = () => (
  <div className="flex h-full w-full items-center justify-center">
    <Spinner className="h-6 w-6" />
  </div>
);

// The curation pages lived at the top level before they moved under /curation.
function LegacyCurationRedirect() {
  const { pathname, search } = useLocation();
  return <Navigate to={`/curation${pathname}${search}`} replace />;
}

export function AppRoutes() {
  const { routes } = useExtensionRegistry();

  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/pending-approval" element={<PendingApprovalPage />} />

        <Route element={<RootLayout />}>
          <Route index element={<HomePage />} />
          <Route path="user-management" element={<UserManagementPage />} />

          <Route path="curation">
            <Route index element={<CurationPage />} />

            <Route path="pdf-upload/:projectId" element={<PdfUploadProjectLayout />}>
              <Route index element={<PdfUploadProjectPage />} />
              <Route path=":reportId" element={<PdfUploadReportPage />} />
            </Route>

            <Route path="projects/:projectId" element={<ProjectsProjectLayout />}>
              <Route index element={<ProjectsProjectPage />} />
              <Route path=":reportId" element={<ProjectsReportPage />} />
            </Route>

            <Route path="review/:projectId" element={<ReviewProjectLayout />}>
              <Route index element={<ReviewProjectPage />} />
              <Route path=":reportId" element={<ReviewReportPage />} />
            </Route>
          </Route>

          <Route path="pdf-upload/*" element={<LegacyCurationRedirect />} />
          <Route path="projects/*" element={<LegacyCurationRedirect />} />
          <Route path="review/*" element={<LegacyCurationRedirect />} />

          {routes}
        </Route>
      </Routes>
    </Suspense>
  );
}
