import { Box, File, FileImage, FileJson, FileSpreadsheet, FileText } from "lucide-react";

export const fileIcon = (name: string) => {
  const ext = name.split(".").pop()?.toLowerCase() ?? "";
  if (ext === "pdf" || ["txt", "md", "doc", "docx"].includes(ext)) return FileText;
  if (["png", "jpg", "jpeg", "tif", "tiff", "webp"].includes(ext)) return FileImage;
  if (["xls", "xlsx", "csv"].includes(ext)) return FileSpreadsheet;
  if (["json", "xml"].includes(ext)) return FileJson;
  if (["ifc", "step", "stp", "dwg", "dxf", "obj", "glb", "nwd"].includes(ext)) return Box;
  return File;
};
export const fmtSize = (b: number) => (b > 1e6 ? `${(b / 1e6).toFixed(1)} MB` : b > 1e3 ? `${(b / 1e3).toFixed(0)} kB` : `${b} B`);

