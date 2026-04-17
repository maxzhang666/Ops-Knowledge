import { useRef, useState } from "react"
import { Upload } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { knowledgeApi } from "@/api/knowledge"

// Must match backend limits (`app/knowledge/document_service.py`)
const MAX_FILE_BYTES = 100 * 1024 * 1024  // 100 MB single-file limit
const ACCEPT_EXT = [".pdf", ".docx", ".doc", ".txt", ".md", ".html", ".csv", ".xlsx", ".pptx"]

function prevalidate(file: File): string | null {
  if (file.size === 0) return "文件为空"
  if (file.size > MAX_FILE_BYTES) {
    const mb = (file.size / 1024 / 1024).toFixed(1)
    return `文件过大 (${mb} MB)，最大 ${MAX_FILE_BYTES / 1024 / 1024} MB`
  }
  const name = file.name.toLowerCase()
  const ok = ACCEPT_EXT.some((ext) => name.endsWith(ext))
  if (!ok) return `不支持的文件类型：${name.split(".").pop() ?? "未知"}`
  return null
}

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

    // Front-end precheck — avoid wasting bandwidth + giving a long wait for
    // a guaranteed 4xx from the backend.
    const err = prevalidate(file)
    if (err) {
      toast.error(err)
      if (inputRef.current) inputRef.current.value = ""
      return
    }

    setUploading(true)
    try {
      await knowledgeApi.uploadDocument(kbId, file, folderId ?? undefined)
      toast.success(`已上传 ${file.name}`)
      onUploaded()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "上传失败")
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
        accept={ACCEPT_EXT.join(",")}
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
