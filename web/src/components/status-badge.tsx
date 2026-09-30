import { Badge } from "@/components/ui/badge";
import { statusLabel, statusTone } from "@/lib/domain";

export function StatusBadge({ status }: { status: string }) {
  return <Badge variant={statusTone(status)}>{statusLabel(status)}</Badge>;
}
