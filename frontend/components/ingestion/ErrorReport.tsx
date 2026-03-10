"use client";

interface Props {
  uploadId: string;
}

export function ErrorReport({ uploadId }: Props) {
  const onDownload = async () => {
    const token = localStorage.getItem("kyros_access_token");
    const response = await fetch(
      `${process.env.NEXT_PUBLIC_API_URL}/api/v1/ingestion/uploads/${uploadId}/errors`,
      { headers: token ? { Authorization: `Bearer ${token}` } : {} }
    );
    if (!response.ok) return;
    const blob = await response.blob();
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `upload-errors-${uploadId}.csv`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    window.URL.revokeObjectURL(url);
  };

  return (
    <button className="text-xs font-medium text-slate-700 underline" onClick={onDownload}>
      Download error report
    </button>
  );
}
