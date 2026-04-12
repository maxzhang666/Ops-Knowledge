import { useRef, useState } from "react"
import { Upload } from "lucide-react"
import { Button } from "@/components/ui/button"
import { knowledgeApi } from "@/api/knowledge"

interface DocumentUploadProps {
  kbId: string
  folderId: string | null
  onUploaded: () => void
}

export function DocumentUpload({ kbId, folderId, onUploaded }: DocumentUploadProps) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)

  async function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return

    setUploading(true)
    try {
      await knowledgeApi.uploadDocument(kbId, file, folderId ?? undefined)
      onUploaded()
    } finally {
      setUploading(false)
      if (inputRef.current) inputRef.current.value = ""
    }
  }

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".pdf,.docx,.txt,.md,.html,.csv,.xlsx"
        className="hidden"
        onChange={handleChange}
      />
      <Button
        variant="outline"
        size="sm"
        disabled={uploading}
        onClick={() => inputRef.current?.click()}
      >
        <Upload className="mr-1 size-3.5" />
        {uploading ? "上传中..." : "上传文档"}
      </Button>
    </>
  )
}
