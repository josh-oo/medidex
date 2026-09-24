import { KeycloakRedirect } from "@/components/auth/keycloak-redirect";

export default function LoginPage() {
  return <KeycloakRedirect action="login" />;
}
