import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";

interface LoadMoreStudiesButtonProps {
  onClick?: () => void;
  loading?: boolean;
}

export function LoadMoreStudiesButton({ onClick, loading }: LoadMoreStudiesButtonProps) {
  return (
    <div className="flex justify-center pt-4 pb-2">
      <Button
        variant="outline"
        onClick={onClick}
        disabled={loading}
        className="min-w-32"
      >
        {loading ? <Spinner /> : "Load More"}
      </Button>
    </div>
  );
}
