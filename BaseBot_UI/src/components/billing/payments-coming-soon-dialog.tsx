"use client";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Modal } from "@/components/ui/modal";

/**
 * Honest bridge for the launch period: paid plans are visible but there is no
 * payment provider yet, so no button may pretend to charge a card.
 */
export function PaymentsComingSoonDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Paid plans are coming soon"
      size="sm"
      footer={
        <div className="flex flex-wrap justify-end gap-2">
          <Button asChild variant="secondary">
            <Link href="/pricing">See all plans</Link>
          </Button>
          <Button variant="primary" onClick={onClose}>
            Got it
          </Button>
        </div>
      }
    >
      <div className="flex flex-col gap-3 text-sm leading-6 text-secondary">
        <p>
          Payments are not configured yet, so every workspace is on the Free
          plan during launch. Nothing will be charged and there is no card on
          file.
        </p>
        <p>
          Standard and Pro are shown so you can see exactly what will be
          available. When billing goes live, you will be able to upgrade from
          this page and your documents, agents and conversations will stay
          exactly as they are.
        </p>
      </div>
    </Modal>
  );
}
