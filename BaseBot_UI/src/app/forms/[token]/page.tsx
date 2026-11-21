import { PublicFormView } from "@/components/forms/public-form-view";

export const metadata = {
  title: "Form",
  robots: { index: false, follow: false },
};

export default async function PublicFormPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <PublicFormView token={token} />;
}
