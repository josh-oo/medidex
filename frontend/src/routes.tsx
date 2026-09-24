import { Routes, Route } from "react-router-dom";

import LoginPage from "./app/(auth)/login/page";
import RegisterPage from "./app/(auth)/register/page";
import PendingApprovalPage from "./app/(auth)/pending-approval/page";

import RootLayout from "./app/(root)/layout";
import HomePage from "./app/(root)/page";
import ApiKeysPage from "./app/(root)/settings/api-keys/page";
import UserManagementPage from "./app/(root)/user-management/page";

import PdfUploadProjectLayout from "./app/(root)/pdf-upload/[projectId]/layout";
import PdfUploadProjectPage from "./app/(root)/pdf-upload/[projectId]/page";
import PdfUploadReportPage from "./app/(root)/pdf-upload/[projectId]/[reportId]/page";

import ProjectsProjectLayout from "./app/(root)/projects/[projectId]/layout";
import ProjectsProjectPage from "./app/(root)/projects/[projectId]/page";
import ProjectsReportPage from "./app/(root)/projects/[projectId]/[reportId]/page";

import ReviewProjectLayout from "./app/(root)/review/[projectId]/layout";
import ReviewProjectPage from "./app/(root)/review/[projectId]/page";
import ReviewReportPage from "./app/(root)/review/[projectId]/[reportId]/page";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/pending-approval" element={<PendingApprovalPage />} />

      <Route element={<RootLayout />}>
        <Route index element={<HomePage />} />
        <Route path="settings/api-keys" element={<ApiKeysPage />} />
        <Route path="user-management" element={<UserManagementPage />} />

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
    </Routes>
  );
}
