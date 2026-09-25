import { Routes, Route } from "react-router-dom";

import LoginPage from "./routes/auth/login/page";
import RegisterPage from "./routes/auth/register/page";
import PendingApprovalPage from "./routes/auth/pending-approval/page";

import RootLayout from "./routes/main/layout";
import HomePage from "./routes/main/page";
import ApiKeysPage from "./routes/main/settings/api-keys/page";
import UserManagementPage from "./routes/main/user-management/page";

import PdfUploadProjectLayout from "./routes/main/pdf-upload/projectId/layout";
import PdfUploadProjectPage from "./routes/main/pdf-upload/projectId/page";
import PdfUploadReportPage from "./routes/main/pdf-upload/projectId/reportId/page";

import ProjectsProjectLayout from "./routes/main/projects/projectId/layout";
import ProjectsProjectPage from "./routes/main/projects/projectId/page";
import ProjectsReportPage from "./routes/main/projects/projectId/reportId/page";

import ReviewProjectLayout from "./routes/main/review/projectId/layout";
import ReviewProjectPage from "./routes/main/review/projectId/page";
import ReviewReportPage from "./routes/main/review/projectId/reportId/page";

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
