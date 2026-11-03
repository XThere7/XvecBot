"use client";

import * as React from "react";
import { Globe2, ScanLine } from "lucide-react";
import { Button } from "@/components/ui/button";
import { FieldControl } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, type SelectOption } from "@/components/ui/select";
import { toast } from "@/lib/toast";
import { useBilling } from "@/hooks/use-billing";
import { useCreateWebsiteSource, websiteErrorMessage } from "@/hooks/use-websites";
import {
  normaliseWebsiteFormUrl,
  toAbsoluteWebsiteUrl,
  websiteFormSchema,
  websiteUrlError,
} from "@/schemas/website";
import type { WebsiteRefreshPolicy } from "@/types/api";

const REFRESH_OPTIONS: SelectOption[] = [
  { value: "manual", label: "Manual", note: "You refresh it" },
  { value: "weekly", label: "Weekly", note: "Every 7 days" },
  { value: "daily", label: "Daily", note: "Every 24 hours" },
];

const POLICY_RANK: Record<WebsiteRefreshPolicy, number> = {
  manual: 0,
  weekly: 1,
  daily: 2,
};

const POLICY_HINTS: Record<WebsiteRefreshPolicy, string> = {
  manual: "We scan the site once. Refresh it whenever you want updated pages.",
  weekly: "We re-check the site every week and update changed pages.",
  daily: "We re-check the site every day and update changed pages.",
};

export function WebsiteConnectForm({ wsId }: { wsId: string }) {
  const create = useCreateWebsiteSource(wsId);
  const billing = useBilling(wsId);
  const [url, setUrl] = React.useState("");
  const [name, setName] = React.useState("");
  const [policy, setPolicy] = React.useState<WebsiteRefreshPolicy>("manual");
  const [urlError, setUrlError] = React.useState<string | null>(null);
  const [formError, setFormError] = React.useState<string | null>(null);
  const urlRef = React.useRef<HTMLInputElement | null>(null);

  const allowedPolicy =
    billing.data?.plan.limits.website_refresh ?? "manual";
  const refreshOptions = REFRESH_OPTIONS.filter(
    (option) =>
      POLICY_RANK[option.value as WebsiteRefreshPolicy] <=
      POLICY_RANK[allowedPolicy],
  );
  const pageLimit = billing.data?.plan.limits.pages_indexed;

  React.useEffect(() => {
    if (POLICY_RANK[policy] > POLICY_RANK[allowedPolicy]) {
      setPolicy(allowedPolicy);
    }
  }, [allowedPolicy, policy]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError(null);

    const parsed = websiteFormSchema.safeParse({
      url,
      name,
      refresh_policy: policy,
    });
    if (!parsed.success) {
      const issue = parsed.error.issues.find((item) => item.path[0] === "url");
      setUrlError(issue?.message ?? "Check the website address.");
      urlRef.current?.focus();
      return;
    }

    setUrlError(null);
    try {
      await create.mutateAsync({
        url: normaliseWebsiteFormUrl(parsed.data.url),
        name: parsed.data.name || undefined,
        refresh_policy: parsed.data.refresh_policy,
      });
      setUrl("");
      setName("");
      toast.success({
        title: "Website added",
        description: "We are scanning its public pages now. Indexed pages will appear below.",
      });
    } catch (error) {
      setFormError(websiteErrorMessage(error));
    }
  };

  return (
    <form onSubmit={(event) => void handleSubmit(event)} className="flex flex-col gap-4">
      <FieldControl
        label="Website address"
        required
        error={urlError ?? undefined}
        hint={`The site's home page, or a specific public section. ${
          pageLimit === null
            ? "We discover and index its public pages."
            : `We scan up to ${pageLimit} indexed pages.`
        }`}
      >
        <Input
          ref={urlRef}
          type="text"
          inputMode="url"
          autoComplete="url"
          spellCheck={false}
          placeholder="https://docs.example.com"
          value={url}
          prefixIcon={<Globe2 />}
          invalid={Boolean(urlError)}
          onChange={(event) => {
            setUrl(event.target.value);
            if (urlError) setUrlError(null);
            if (formError) setFormError(null);
          }}
          onBlur={() => {
            if (!url.trim()) return;
            const absolute = toAbsoluteWebsiteUrl(url);
            if (absolute !== url) setUrl(absolute);
            setUrlError(websiteUrlError(absolute));
          }}
        />
      </FieldControl>

      <div className="grid gap-4 sm:grid-cols-2">
        <FieldControl
          label="Name (optional)"
          hint="Shown in this list. Defaults to the domain."
          counter={`${name.length}/100`}
        >
          <Input
            value={name}
            maxLength={100}
            placeholder="Product documentation"
            onChange={(event) => {
              setName(event.target.value);
              if (formError) setFormError(null);
            }}
          />
        </FieldControl>

        <FieldControl label="Refresh" hint={POLICY_HINTS[policy]}>
          <Select
            options={refreshOptions}
            value={policy}
            onValueChange={(value) => setPolicy(value as WebsiteRefreshPolicy)}
          />
        </FieldControl>
      </div>

      {formError && (
        <p
          role="alert"
          className="rounded-sm border border-danger-500/30 bg-danger-500/10 px-3 py-2 text-xs text-danger-400"
        >
          {formError}
        </p>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="max-w-lg text-xs text-tertiary">
          Public pages only. Pages behind a login, PDFs and JavaScript-only
          pages are skipped.
        </p>
        <Button
          type="submit"
          variant="primary"
          loading={create.isPending}
          iconLeft={<ScanLine aria-hidden className="h-4 w-4" />}
          className="w-full sm:w-auto"
        >
          {create.isPending ? "Starting scan…" : "Connect website"}
        </Button>
      </div>
    </form>
  );
}
