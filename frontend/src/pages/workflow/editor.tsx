import { useParams } from "react-router-dom"
import { WorkflowEditor } from "@/features/workflow/editor"

export default function WorkflowEditorPage() {
  const { id } = useParams()
  if (!id) return null
  return <WorkflowEditor workflowId={id} />
}
