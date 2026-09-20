export default function ReportDetailsNotFound() {
  return (
    <div className="flex h-full min-h-[320px] flex-col items-center justify-center rounded-2xl border border-dashed border-border bg-card/70 p-8 text-center">
      <div className="space-y-2">
        <p className="text-lg font-semibold">Report details unavailable</p>
        <p className="text-sm text-muted-foreground">
          We could not find similar studies for this report. Please pick another report from the list.
        </p>
      </div>
    </div>
  );
}
