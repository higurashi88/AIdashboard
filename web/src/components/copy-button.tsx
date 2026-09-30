import { useEffect, useState } from "react";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface CopyButtonProps {
  text: string;
  label: string;
  className?: string;
}

export function CopyButton({ text, label, className }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timeout = window.setTimeout(() => setCopied(false), 2000);
    return () => window.clearTimeout(timeout);
  }, [copied]);

  async function copyText() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch (error) {
      console.error("Failed to copy text", error);
    }
  }

  const accessibleLabel = copied ? "コピーしました" : label;
  return (
    <Button type="button" size="icon" variant="ghost" className={cn("size-7 shrink-0", className)} onClick={copyText} aria-label={accessibleLabel} title={accessibleLabel}>
      {copied ? <Check className="size-3.5 text-emerald-600 dark:text-emerald-400" /> : <Copy className="size-3.5" />}
    </Button>
  );
}
