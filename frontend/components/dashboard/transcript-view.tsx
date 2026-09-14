"use client";

import { motion } from "framer-motion";
import { MessageSquare } from "lucide-react";
import type { ConversationTurn } from "@/lib/types";
import { formatTime } from "@/lib/format";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { EmptyState } from "@/components/dashboard/empty-state";
import { cn } from "@/lib/utils";

export function TranscriptView({ turns, className }: { turns: ConversationTurn[]; className?: string }) {
  if (!turns || turns.length === 0) {
    return (
      <Card className={className}>
        <EmptyState
          icon={MessageSquare}
          title="No conversation recorded"
          description="Turns appear here as the patient speaks with the voice assistant."
        />
      </Card>
    );
  }

  return (
    <Card className={cn("flex min-h-0 flex-col overflow-hidden", className)}>
      <CardHeader className="pb-3">
        <CardTitle>Full transcript</CardTitle>
        <p className="text-xs text-ink-muted">
          {turns.length} turns · verbatim record of the intake conversation
        </p>
      </CardHeader>
      <CardContent className="thin-scroll min-h-0 flex-1 space-y-3 overflow-y-auto">
        {turns.map((turn, index) => {
          const isPatient = turn.role === "patient";
          return (
            <motion.div
              key={turn.id}
              initial={{ opacity: 0, y: 4 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.15, delay: Math.min(index * 0.012, 0.25) }}
              className={cn("flex flex-col", isPatient ? "items-start" : "items-end")}
            >
              <div className="mb-1 flex items-center gap-2 px-1">
                <span
                  className={cn(
                    "text-[10px] font-bold uppercase tracking-wider",
                    isPatient ? "text-pine" : "text-marigold-deep"
                  )}
                >
                  {isPatient ? "Patient" : "Assistant"}
                </span>
                <span className="tabular text-[10px] text-ink-faint">{formatTime(turn.created_at)}</span>
              </div>
              <div
                className={cn(
                  "max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
                  isPatient
                    ? "rounded-tl-md bg-mint text-ink"
                    : "rounded-tr-md bg-pine text-mint"
                )}
              >
                {turn.content}
                {turn.interrupted && (
                  <span className="mt-1 block text-[10px] italic opacity-70">
                    interrupted by the patient
                  </span>
                )}
              </div>
            </motion.div>
          );
        })}
      </CardContent>
    </Card>
  );
}
