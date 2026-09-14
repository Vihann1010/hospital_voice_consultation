"use client";

/** The theatre list at the ward terminal, where theatre nurses sign in. */
import { TheatreBoard } from "@/components/theatre/theatre-board";

export default function WardTheatrePage() {
  return (
    <div className="mx-auto max-w-[1400px] space-y-4 px-4 py-5 sm:px-6">
      <h1 className="font-display text-xl font-semibold text-pine">Theatre</h1>
      <TheatreBoard basePath="/ward/theatre" />
    </div>
  );
}
