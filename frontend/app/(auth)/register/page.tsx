import { KeycloakRedirect } from "@/components/auth/keycloak-redirect";

export default function RegisterPage() {
  return <KeycloakRedirect action="register" />;
}
