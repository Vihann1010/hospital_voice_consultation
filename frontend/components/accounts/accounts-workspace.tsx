"use client";

/** The books: posting and trial balance, ledgers, the day book, consultant payouts. */
import { useState } from "react";
import { canManageAccounts } from "@/lib/types/accounts";
import { useAuth } from "@/components/dashboard/auth-provider";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BooksPanel } from "@/components/accounts/books-panel";
import { DayBookPanel } from "@/components/accounts/day-book-panel";
import { LedgersPanel } from "@/components/accounts/ledgers-panel";
import { PayoutsPanel } from "@/components/accounts/payouts-panel";

export function AccountsWorkspace() {
  const { user } = useAuth();
  const canManage = canManageAccounts(user?.role);
  const [tab, setTab] = useState("books");
  const [ledgerId, setLedgerId] = useState<string | null>(null);

  return (
    <Tabs value={tab} onValueChange={setTab}>
      <TabsList className="mb-4 w-fit">
        <TabsTrigger value="books">Books</TabsTrigger>
        <TabsTrigger value="ledgers">Ledgers</TabsTrigger>
        <TabsTrigger value="daybook">Day book</TabsTrigger>
        <TabsTrigger value="payouts">Consultant payouts</TabsTrigger>
      </TabsList>
      <TabsContent value="books">
        <BooksPanel canManage={canManage} onOpenLedger={(id) => { setLedgerId(id); setTab("ledgers"); }} />
      </TabsContent>
      <TabsContent value="ledgers">
        <LedgersPanel canManage={canManage} selectedId={ledgerId} onSelect={setLedgerId} />
      </TabsContent>
      <TabsContent value="daybook">
        <DayBookPanel canManage={canManage} />
      </TabsContent>
      <TabsContent value="payouts">
        <PayoutsPanel canManage={canManage} />
      </TabsContent>
    </Tabs>
  );
}
