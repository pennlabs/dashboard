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

export const useDeployment = (namespace: string, name: string) =>
  useQuery({
    queryKey: ["deployment", namespace, name],
    queryFn: () => api.getDeployment(namespace, name),
    refetchInterval: 15000,
    enabled: Boolean(namespace && name),
  })

export const usePods = (namespace: string, name: string) =>
  useQuery({
    queryKey: ["pods", namespace, name],
    queryFn: () => api.getPods(namespace, name),
    refetchInterval: 10000,
    enabled: Boolean(namespace && name),
  })

export const useRollback = (namespace: string, name: string) => {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (image: string) => api.rollback(namespace, name, image),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["deployment", namespace, name] })
      qc.invalidateQueries({ queryKey: ["products"] })
    },
  })
}
