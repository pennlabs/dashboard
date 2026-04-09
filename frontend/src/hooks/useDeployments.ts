import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import * as api from "../api"

export const useProducts = () =>
  useQuery({
    queryKey: ["products"],
    queryFn: api.getProducts,
    refetchInterval: 15000,
  })

export const useProduct = (name: string) =>
  useQuery({
    queryKey: ["product", name],
    queryFn: () => api.getProduct(name),
    refetchInterval: 15000,
    enabled: Boolean(name),
  })

export const useDeployment = (id: number) =>
  useQuery({
    queryKey: ["deployment", id],
    queryFn: () => api.getDeployment(id),
    refetchInterval: 15000,
    enabled: Number.isFinite(id) && id > 0,
  })

export const usePods = (id: number) =>
  useQuery({
    queryKey: ["pods", id],
    queryFn: () => api.getPods(id),
    refetchInterval: 10000,
    enabled: Number.isFinite(id) && id > 0,
  })

export const useRollback = (deploymentId: number) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (image: string) => api.rollback(deploymentId, image),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["deployment", deploymentId] })
      qc.invalidateQueries({ queryKey: ["products"] })
    },
  })
}
