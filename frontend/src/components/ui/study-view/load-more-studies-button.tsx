import { Button } from "@/components/ui/button";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

export function LoadMoreStudiesButton() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  const currentLimit = Number(searchParams.get("k") ?? "10");
  const nextLimit = currentLimit + 10;

  return (
    <div className="flex justify-center pt-4 pb-2">
      <Button
        variant="outline"
        onClick={() => {
          const params = new URLSearchParams(searchParams.toString());
          params.set("k", String(nextLimit));
          const queryString = params.toString();
          navigate(queryString ? `${pathname}?${queryString}` : pathname);
        }}
        className="min-w-32"
      >
        Load More
      </Button>
    </div>
  );
}
