from dataclasses import dataclass
from math import exp, fsum, sqrt, log1p, expm1, isfinite
from .contracts import PredictedClaim


@dataclass(frozen=True)
class Predictor:
    center: tuple
    scale: tuple
    cost_bias: float
    cost_weights: tuple
    failure_bias: float
    failure_weights: tuple
    observations: int


def stable_probability(logit):
    atom=exp(-abs(logit))
    return 1/(1+atom) if logit>=0 else atom/(1+atom)


def fit(examples, *, penalty=.12):
    if len(examples)<6 or penalty<0:
        raise ValueError("INCOMPLETE_COHORT")
    inputs, cents, labels = zip(*examples,strict=True)
    columns=list(zip(*inputs, strict=True))
    center=tuple(fsum(column)/len(column) for column in columns)
    scale=tuple(max(1e-5,sqrt(fsum((value-mu)**2 for value in col)/len(col))) for col,mu in zip(columns,center,strict=True))
    features=[tuple((value-mu)/width for value,mu,width in zip(row,center,scale,strict=True)) for row in inputs]
    transformed=[log1p(value) for value in cents]
    cost_bias=fsum(transformed)/len(features)
    fail_bias=0.0
    cost=[0.0]*len(center)
    risk=[0.0]*len(center)
    for _ in range(94):
        cost_error=[]
        risk_error=[]
        for row, price, label in zip(features,transformed,labels,strict=True):
            fitted_cost=cost_bias+fsum(w*x for w,x in zip(cost,row,strict=True))
            fitted_risk=fail_bias+fsum(w*x for w,x in zip(risk,row,strict=True))
            cost_error.append(max(-1.75,min(1.75,fitted_cost-price)))
            risk_error.append(stable_probability(fitted_risk)-label)
        step=.12/len(features)
        cost_bias -= step*fsum(cost_error)
        fail_bias -= step*fsum(risk_error)
        for j in range(len(center)):
            cost[j] -= step*fsum(e*x[j] for e,x in zip(cost_error,features,strict=True)) + .12*penalty*cost[j]
            risk[j] -= step*fsum(e*x[j] for e,x in zip(risk_error,features,strict=True)) + .12*penalty*risk[j]
    return Predictor(center,scale,cost_bias,tuple(cost),fail_bias,tuple(risk),len(features))


def score(predictor, points):
    z = [(value-mu)/width for value,mu,width in zip(points,predictor.center,predictor.scale,strict=True)]
    cost=expm1(max(0,min(17,predictor.cost_bias+fsum(w*x for w,x in zip(predictor.cost_weights,z,strict=True)))))
    risk=stable_probability(predictor.failure_bias+fsum(w*x for w,x in zip(predictor.failure_weights,z,strict=True)))
    return cost,risk,sqrt(fsum(x*x for x in z))


def validate(predictions):
    points=sorted((p,label,actual-fitted) for p,label,actual,fitted in predictions if isfinite(p) and isfinite(actual) and isfinite(fitted))
    positive=sum(label for _,label,_ in points)
    n=len(points)
    if not n:
        return {"support":0,"recall":None,"brier":None,"residual_median":None}
    errors=sorted(error for _,_,error in points)
    return {"support":n,"recall":sum(label and p>=.5 for p,label,_ in points)/positive if positive else None,
            "brier":fsum((p-label)**2 for p,label,_ in points)/n,"residual_median":errors[n//2]}
